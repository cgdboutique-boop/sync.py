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
- SWAPS supplier title <-> description (HTML removed, title trimmed for SEO)

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
import re
import requests

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
            return resp
        except Exception as e:
            last_exc = e
            continue
    raise last_exc

def clean_text(text):
    text = re.sub(r'<[^>]+>', '', text or '')      # remove HTML tags
    text = re.sub(r'\s+', ' ', text).strip()      # remove extra whitespace
    return text

def remove_sku(text):
    return re.sub(r'#\d+', '', text).strip()

def shorten(text, max_len=70):
    if len(text) <= max_len:
        return text
    cut = text[:max_len].rsplit(' ', 1)[0]
    return cut + "…"

# ---------- Supplier / Shopify Fetch ----------
def read_supplier_products(limit=SUPPLIER_PAGE_LIMIT):
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
        ids = [p.get("id") for p in data if isinstance(p.get("id"), (int, float))]
        if not ids:
            break
        since_id = max(ids)
    print(f"✅ Total supplier products fetched: {len(products)}")
    return products

def fetch_shopify_products_all():
    products = []
    since_id = 0
    base = f"https://{SHOPIFY_STORE}/admin/api/{SHOPIFY_API_VERSION}/products.json"
    print("📦 Fetching all products from Shopify...")
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

def build_shopify_index(shopify_products):
    idx = {"tags": {}, "sku": {}, "handle": {}}
    for p in shopify_products:
        tags_str = p.get("tags", "")
        if tags_str:
            tags = [t.strip() for t in tags_str.split(",") if t.strip()]
            for t in tags:
                if t.startswith("supplier:"):
                    idx["tags"][t] = p
        for v in p.get("variants", []):
            sku = (v.get("sku") or "").strip()
            if sku:
                idx["sku"][sku] = p
        handle = p.get("handle")
        if handle:
            idx["handle"][handle] = p
    return idx

# ---------- Payload Builder (title/description swap) ----------
def normalize_price(p):
    try:
        return str(round(float(p), 2))
    except Exception:
        return None

def make_fallback_sku(supplier_product_id, variant_index):
    return f"{supplier_product_id}-{variant_index}"

def build_shopify_product_payload(supplier_prod):
    supplier_id = supplier_prod.get("id")
    supplier_title = clean_text(supplier_prod.get("title") or "")
    supplier_desc = clean_text(supplier_prod.get("body_html") or "")

    # SWAP title <-> description
    new_title = shorten(remove_sku(supplier_desc), 70)
    new_body = supplier_title  # keep SKU in description

    tags = supplier_prod.get("tags") or ""
    supplier_tag = f"supplier:{supplier_id}"
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    if supplier_tag not in tag_list:
        tag_list.append(supplier_tag)

    images = [{"src": img.get("src")} for img in (supplier_prod.get("images") or []) if img.get("src")]

    variants = []
    for i, v in enumerate(supplier_prod.get("variants") or []):
        sku = (v.get("sku") or "").strip() or make_fallback_sku(supplier_id, i+1)
        price = normalize_price(v.get("price")) or "0.00"
        inv_qty = v.get("inventory_quantity")
        var_payload = {
            "option1": v.get("option1"),
            "option2": v.get("option2"),
            "option3": v.get("option3"),
            "sku": sku,
            "price": price,
            "inventory_management": "shopify" if v.get("inventory_management") else None
        }
        if isinstance(inv_qty, int):
            var_payload["inventory_quantity"] = inv_qty
        variants.append(var_payload)

    payload = {
        "product": {
            "title": new_title,
            "body_html": new_body,
            "vendor": TARGET_VENDOR,
            "tags": ", ".join(tag_list),
            "images": images if images else None,
            "variants": variants if variants else None
        }
    }

    # remove None
    def clean(o):
        if isinstance(o, dict):
            return {k: clean(v) for k, v in o.items() if v is not None}
        if isinstance(o, list):
            return [clean(v) for v in o if v is not None]
        return o
    return clean(payload)

# ---------- Shopify CRUD ----------
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

# ---------- Main Sync ----------
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

        found_product = shop_idx["tags"].get(f"supplier:{supplier_id}")

        if not found_product:
            sku_candidates = [(v.get("sku") or "").strip() for v in (sp.get("variants") or []) if (v.get("sku") or "").strip()]
            for sku in sku_candidates:
                if sku in shop_idx["sku"]:
                    found_product = shop_idx["sku"][sku]
                    break

        if not found_product and sp.get("handle"):
            found_product = shop_idx["handle"].get(sp.get("handle"))

        payload = build_shopify_product_payload(sp)

        if found_product:
            product_id = found_product.get("id")
            update_payload = {"product": payload["product"]}
            update_payload["product"]["vendor"] = TARGET_VENDOR
            res = update_shopify_product(product_id, update_payload, dry_run=dry_run)
            if dry_run:
                report.append(f"DRY-UPDATE: supplier:{supplier_id} -> shopify:{product_id}")
            else:
                if isinstance(res, dict) and res.get("status") and int(res["status"]) in (200, 201):
                    updated += 1
                    report.append(f"UPDATED: supplier:{supplier_id} -> shopify:{product_id} (status {res['status']})")
                    shop_idx["tags"][f"supplier:{supplier_id}"] = found_product
                else:
                    errors += 1
                    report.append(f"ERROR-UPD: supplier:{supplier_id} -> shopify:{product_id} resp: {res}")
        else:
            if dry_run:
                report.append(f"DRY-CREATE: supplier:{supplier_id} -> would create new product")
            else:
                res = create_shopify_product(payload, dry_run=dry_run)
                if isinstance(res, dict) and res.get("status") and int(res["status"]) in (200, 201):
                    created += 1
                    body = res.get("body") or {}
                    newp = (body.get("product") if isinstance(body, dict) else None)
                    nid = newp.get("id") if newp else "unknown"
                    report.append(f"CREATED: supplier:{supplier_id} -> shopify:{nid} (status {res['status']})")
                    shop_idx["tags"][f"supplier:{supplier_id}"] = newp or {}
                else:
                    errors += 1
                    report.append(f"ERROR-CREATE: supplier:{supplier_id} resp: {res}")

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
    with open("sync_report.txt", "w", encoding="utf-8") as f:
        f.write(f"Sync started. Dry run: {args.dry_run}\n")
    sync_all(dry_run=args.dry_run, limit=args.limit)
