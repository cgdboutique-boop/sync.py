#!/usr/bin/env python3
"""
sync.py

Supplier -> Shopify sync (match by supplier product id)

Features:
- Matches by supplier product id (tag: supplier:<id>) OR by variant SKU
- Creates products when not found, updates when found
- Overrides vendor to "CGD Kids Boutique"
- Generates fallback SKUs for missing SKUs
- Attaches images (uses supplier images[*].src)
- Produces sync_report.txt
- Dry-run mode supported

Env vars required:
- SHOPIFY_STORE
- SHOPIFY_TOKEN
- SUPPLIER_API_URL
- SUPPLIER_TOKEN

Optional:
- SHOPIFY_API_VERSION (default: 2025-07)
"""

import os
import time
import json
import argparse
import requests
from collections import defaultdict

# ---------- Configuration ----------
DEFAULT_SHOPIFY_API_VERSION = os.environ.get("SHOPIFY_API_VERSION", "2025-07")
TARGET_VENDOR = "CGD Kids Boutique"
RATE_LIMIT_SLEEP = 0.55   # seconds between Shopify API calls (~1.8 calls/sec)
RETRY_BACKOFF = [1, 2, 5]  # seconds for retries on connection errors
SUPPLIER_PAGE_LIMIT = 250

# ---------- Environment (required) ----------
SHOPIFY_STORE = os.environ.get("SHOPIFY_STORE")
SHOPIFY_TOKEN = os.environ.get("SHOPIFY_TOKEN")
SUPPLIER_API_URL = os.environ.get("SUPPLIER_API_URL")
SUPPLIER_TOKEN = os.environ.get("SUPPLIER_TOKEN")
SHOPIFY_API_VERSION = DEFAULT_SHOPIFY_API_VERSION

for name in ("SHOPIFY_STORE", "SHOPIFY_TOKEN", "SUPPLIER_API_URL", "SUPPLIER_TOKEN"):
    if not globals().get(name):
        raise SystemExit(f"Missing required env var: {name}")

supplier_headers = {
    "X-Shopify-Access-Token": SUPPLIER_TOKEN,
    "Accept": "application/json"
}
shopify_headers = {
    "X-Shopify-Access-Token": SHOPIFY_TOKEN,
    "Content-Type": "application/json"
}

# ---------- Utilities ----------
def safe_request(method, url, headers=None, params=None, json_body=None, data=None, allow_non200=False):
    """Simple safe request with retries and spacing."""
    last_exc = None
    for wait in [0] + RETRY_BACKOFF:
        if wait:
            time.sleep(wait)
        try:
            if json_body is not None:
                resp = requests.request(method, url, headers=headers, params=params, json=json_body, timeout=60)
            else:
                resp = requests.request(method, url, headers=headers, params=params, data=data, timeout=60)
            time.sleep(RATE_LIMIT_SLEEP)
            if allow_non200 or resp.status_code < 400:
                return resp
            # For 4xx/5xx, return so caller can handle body
            return resp
        except Exception as e:
            last_exc = e
            continue
    raise last_exc

def read_supplier_products(limit=SUPPLIER_PAGE_LIMIT):
    """Fetch all supplier products (paged by since_id)."""
    products = []
    since_id = 0
    print(f"📥 Fetching supplier products (limit per page = {limit})...")
    while True:
        params = {"limit": limit, "since_id": since_id}
        try:
            r = safe_request("GET", SUPPLIER_API_URL, headers=supplier_headers, params=params)
        except Exception as e:
            print(f"❌ Supplier fetch error: {e}")
            break
        if r.status_code != 200:
            print(f"❌ Supplier API error (since_id {since_id}): {r.status_code} {r.text}")
            break
        body = r.json()
        data = body.get("products", []) if isinstance(body, dict) else []
        if not data:
            break
        products.extend(data)
        print(f"📦 Received {len(data)} new products...")
        # update since_id using numeric supplier product id (assumes supplier id numeric)
        ids = [p.get("id") for p in data if isinstance(p.get("id"), (int, float))]
        if not ids:
            break
        since_id = max(ids)
    print(f"✅ Total supplier products fetched: {len(products)}")
    return products

def fetch_shopify_products_all():
    """Fetch all Shopify products (paged)."""
    products = []
    since_id = 0
    base = f"https://{SHOPIFY_STORE}/admin/api/{SHOPIFY_API_VERSION}/products.json"
    print("📦 Fetching all products from Shopify (this may take a while)...")
    while True:
        params = {"limit": 250, "since_id": since_id}
        try:
            r = safe_request("GET", base, headers=shopify_headers, params=params)
        except Exception as e:
            print(f"❌ Error fetching Shopify products: {e}")
            break
        if r.status_code != 200:
            print(f"❌ Error fetching Shopify products: {r.status_code}")
            break
        data = r.json().get("products", [])
        if not data:
            break
        products.extend(data)
        ids = [p.get("id", 0) for p in data if p.get("id")]
        since_id = max(ids) if ids else 0
    print(f"✅ Found {len(products)} products on Shopify.")
    return products

def find_shopify_product_by_supplier_id(products_index, supplier_id):
    """Primary lookup: by tag supplier:<id> inside product['tags'] string."""
    key = f"supplier:{supplier_id}"
    return products_index.get("tags", {}).get(key)

def build_shopify_index(shopify_products):
    """
    Build multiple indexes for quick lookup:
      - tags: map 'supplier:<id>' -> product
      - sku: map variant.sku -> product
      - handle: map handle -> product
    """
    idx = {"tags": {}, "sku": {}, "handle": {}}
    for p in shopify_products:
        tags_str = p.get("tags", "")
        if tags_str:
            # tags may be comma-separated; normalize keys like 'supplier:123'
            tags = [t.strip() for t in tags_str.split(",") if t.strip()]
            for t in tags:
                if t.startswith("supplier:"):
                    idx["tags"][t] = p
        # variants => sku
        for v in p.get("variants", []):
            sku = (v.get("sku") or "").strip()
            if sku:
                idx["sku"][sku] = p
        handle = p.get("handle")
        if handle:
            idx["handle"][handle] = p
    return idx

def normalize_price(p):
    try:
        return str(round(float(p), 2))
    except Exception:
        return None

def make_fallback_sku(supplier_product_id, variant_index):
    return f"{supplier_product_id}-{variant_index}"

def build_shopify_product_payload(supplier_prod):
    """
    Build Shopify product payload from supplier product object.
    Uses supplier fields: title, body_html, images[*].src, variants[*], tags.
    Ensures vendor override and fallback SKU generation.
    """
    supplier_id = supplier_prod.get("id")
    title = supplier_prod.get("title") or f"Supplier {supplier_id}"
    body_html = supplier_prod.get("body_html") or ""
    tags = supplier_prod.get("tags") or ""
    # ensure supplier tag present for future matching
    supplier_tag = f"supplier:{supplier_id}"
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    if supplier_tag not in tag_list:
        tag_list.append(supplier_tag)

    # build images list suitable for Shopify (list of {"src": ...})
    images = []
    for img in supplier_prod.get("images", []):
        src = img.get("src")
        if src:
            images.append({"src": src})

    # build variants
    variants = []
    for i, v in enumerate(supplier_prod.get("variants", []) or []):
        sku = (v.get("sku") or "").strip()
        if not sku:
            sku = make_fallback_sku(supplier_id, i+1)
        price = normalize_price(v.get("price")) or "0.00"
        inv_qty = v.get("inventory_quantity")
        variant_payload = {
            "option1": v.get("option1") or None,
            "option2": v.get("option2") or None,
            "option3": v.get("option3") or None,
            "sku": sku,
            "price": price,
            "inventory_management": "shopify" if v.get("inventory_management") else None,
        }
        # Shopify accepts inventory_quantity only on creation via variants[].inventory_quantity
        if isinstance(inv_qty, int):
            variant_payload["inventory_quantity"] = inv_qty
        variants.append(variant_payload)

    product_payload = {
        "product": {
            "title": title,
            "body_html": body_html,
            "vendor": TARGET_VENDOR,
            "tags": ", ".join(tag_list),
            "images": images if images else None,
            "variants": variants if variants else None,
            # we do not set handle here; Shopify will create one if not provided
            # but we could set handle: supplier_prod.get('handle')
        }
    }
    # Remove None keys (Shopify dislikes explicit nulls in some fields)
    def clean(o):
        if isinstance(o, dict):
            return {k: clean(v) for k, v in o.items() if v is not None}
        if isinstance(o, list):
            return [clean(v) for v in o if v is not None]
        return o
    product_payload = clean(product_payload)
    return product_payload

# ---------- Shopify CRUD helpers ----------
def create_shopify_product(payload, dry_run=False):
    url = f"https://{SHOPIFY_STORE}/admin/api/{SHOPIFY_API_VERSION}/products.json"
    if dry_run:
        return {"status": "dry-run", "action": "create", "payload": payload}
    r = safe_request("POST", url, headers=shopify_headers, json_body=payload, allow_non200=True)
    try:
        return {"status": r.status_code, "body": r.json()}
    except Exception:
        return {"status": r.status_code, "text": r.text}

def update_shopify_product(product_id, payload, dry_run=False):
    url = f"https://{SHOPIFY_STORE}/admin/api/{SHOPIFY_API_VERSION}/products/{product_id}.json"
    if dry_run:
        return {"status": "dry-run", "action": "update", "product_id": product_id, "payload": payload}
    r = safe_request("PUT", url, headers=shopify_headers, json_body=payload, allow_non200=True)
    try:
        return {"status": r.status_code, "body": r.json()}
    except Exception:
        return {"status": r.status_code, "text": r.text}

def append_sync_report(report_lines):
    with open("sync_report.txt", "a", encoding="utf-8") as f:
        for line in report_lines:
            f.write(line + "\n")

# ---------- Sync logic ----------
def sync_all(dry_run=False, limit=None):
    report = []
    supplier_products = read_supplier_products(limit=limit or SUPPLIER_PAGE_LIMIT)
    shopify_products = fetch_shopify_products_all()
    shop_idx = build_shopify_index(shopify_products)

    created = 0
    updated = 0
    skipped = 0
    errors = 0

    for sp in supplier_products:
        supplier_id = sp.get("id")
        if supplier_id is None:
            report.append(f"SKIP: supplier product missing id: {json.dumps(sp)[:120]}")
            skipped += 1
            continue

        # 1) attempt find by supplier:<id> tag
        found_product = shop_idx["tags"].get(f"supplier:{supplier_id}")

        # 2) fallback: if not found, try match by any variant SKU present
        if not found_product:
            # find first non-empty SKU in supplier variants
            sku_candidates = [(v.get("sku") or "").strip() for v in (sp.get("variants") or []) if (v.get("sku") or "").strip()]
            matched = None
            for sku in sku_candidates:
                if sku in shop_idx["sku"]:
                    matched = shop_idx["sku"][sku]
                    break
            if matched:
                found_product = matched

        # 3) fallback: try match by handle if given
        if not found_product and sp.get("handle"):
            found_product = shop_idx["handle"].get(sp.get("handle"))

        payload = build_shopify_product_payload(sp)

        if found_product:
            # update path: ensure vendor override and merge new tags/images/variants
            product_id = found_product.get("id")
            # Build minimal update payload that preserves vendor override and updates fields that changed.
            update_payload = {"product": payload["product"]}
            # Ensure vendor override
            update_payload["product"]["vendor"] = TARGET_VENDOR
            res = update_shopify_product(product_id, update_payload, dry_run=dry_run)
            if dry_run:
                report.append(f"DRY-UPDATE: supplier:{supplier_id} -> shopify:{product_id}")
            else:
                if isinstance(res, dict) and res.get("status") and int(res["status"]) in (200, 201):
                    updated += 1
                    report.append(f"UPDATED: supplier:{supplier_id} -> shopify:{product_id} (status {res['status']})")
                    # Update local index tags/sku/handle for subsequent matches in this run
                    # Note: We won't re-fetch the full product; just optimistic update of index
                    shop_idx["tags"][f"supplier:{supplier_id}"] = found_product
                else:
                    errors += 1
                    report.append(f"ERROR-UPD: supplier:{supplier_id} -> shopify:{product_id} resp: {res}")
        else:
            # create new product
            if dry_run:
                report.append(f"DRY-CREATE: supplier:{supplier_id} -> would create new product")
            else:
                res = create_shopify_product(payload, dry_run=dry_run)
                if isinstance(res, dict) and res.get("status") and int(res["status"]) in (200, 201):
                    created += 1
                    # Try to extract created product id
                    body = res.get("body") or {}
                    newp = (body.get("product") if isinstance(body, dict) else None)
                    nid = newp.get("id") if newp else "unknown"
                    report.append(f"CREATED: supplier:{supplier_id} -> shopify:{nid} (status {res['status']})")
                    # add to index for subsequent iterations
                    shop_idx["tags"][f"supplier:{supplier_id}"] = newp or {}
                else:
                    errors += 1
                    report.append(f"ERROR-CREATE: supplier:{supplier_id} resp: {res}")

    # summary
    summary = [
        "SYNC SUMMARY",
        f"Total supplier products processed: {len(supplier_products)}",
        f"Created: {created}",
        f"Updated: {updated}",
        f"Skipped: {skipped}",
        f"Errors: {errors}"
    ]
    report = summary + [""] + report
    append_sync_report(report)
    print("\n".join(summary))
    print("Detailed report written to sync_report.txt")

# ---------- CLI ----------
def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true", help="Do not modify Shopify (no POST/PUT/DELETE).")
    p.add_argument("--limit", type=int, default=None, help="Limit supplier page size (for testing).")
    return p.parse_args()

if __name__ == "__main__":
    args = parse_args()
    # Clear or create report file at start
    with open("sync_report.txt", "w", encoding="utf-8") as f:
        f.write(f"Sync started. Dry run: {args.dry_run}\n")
    sync_all(dry_run=args.dry_run, limit=args.limit)
