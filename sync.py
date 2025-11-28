#!/usr/bin/env python3
"""
sync.py
Sync supplier JSON feed -> Shopify (REST 2025-07)
Features:
- Group supplier variants by base SKU (handles "1000121 (90)" -> "1000121")
- Use handle = base_sku.lower().strip()
- Overwrite vendor to "CGD Kids Boutique"
- Update existing Shopify products by handle: update matching variants by SKU, add new variants
- Create product when handle missing
- Rate-limit aware + retries
- Optional duplicate cleanup for vendor "CGD Kids Boutique" (prints what will be removed; enable actual deletion)
"""

import os
import time
import json
import requests
from collections import defaultdict
from datetime import datetime
from urllib.parse import urlencode

# ---------- Config ----------
SHOPIFY_STORE = os.environ["SHOPIFY_STORE"]            # e.g. "your-store.myshopify.com"
SHOPIFY_TOKEN = os.environ["SHOPIFY_TOKEN"]
SUPPLIER_API_URL = os.environ["SUPPLIER_API_URL"]      # Supplier products endpoint (returns JSON with "products" list)
SUPPLIER_TOKEN = os.environ["SUPPLIER_TOKEN"]

# Behavior toggles
DO_DELETE_DUPLICATES = False   # <-- set True to allow script to actually delete duplicates for CGD Kids Boutique
RATE_LIMIT_MIN_INTERVAL = 0.55 # ~1.8 requests/sec (Shopify 2/sec) -> conservative spacing between calls
MAX_RETRIES = 6

# Vendor to force
TARGET_VENDOR = "CGD Kids Boutique"

# Shopify headers
shopify_headers = {
    "X-Shopify-Access-Token": SHOPIFY_TOKEN,
    "Content-Type": "application/json"
}

# Supplier headers
supplier_headers = {
    "Authorization": f"Bearer {SUPPLIER_TOKEN}",
    "Accept": "application/json"
}

# ---------- Helpers ----------

_last_request_time = 0.0

def wait_rate_limit():
    global _last_request_time
    elapsed = time.time() - _last_request_time
    if elapsed < RATE_LIMIT_MIN_INTERVAL:
        time.sleep(RATE_LIMIT_MIN_INTERVAL - elapsed)
    _last_request_time = time.time()

def request_with_retries(method, url, **kwargs):
    """
    Request wrapper with simple retry/backoff for 429 and network errors.
    """
    attempt = 0
    backoff = 1.0
    while attempt < MAX_RETRIES:
        attempt += 1
        wait_rate_limit()
        try:
            resp = requests.request(method, url, headers=kwargs.pop("headers", None) or shopify_headers, timeout=30, **kwargs)
        except requests.exceptions.RequestException as e:
            print(f"⚠️ Request error (attempt {attempt}) for {url}: {e} — retrying in {backoff}s")
            time.sleep(backoff)
            backoff *= 2
            continue

        if resp.status_code in (429, 503):
            # rate limit or service unavailable
            print(f"⚠️ Shopify rate-limit/service ({resp.status_code}) on {url} (attempt {attempt}). Body: {resp.text}")
            time.sleep(backoff)
            backoff *= 2
            continue

        return resp

    raise RuntimeError(f"Max retries reached for {url}")

# ---------- Supplier fetch ----------
def fetch_supplier_products(limit=250):
    products = []
    since_id = 0
    while True:
        params = {"limit": limit, "since_id": since_id}
        try:
            resp = request_with_retries("GET", SUPPLIER_API_URL, params=params, headers=supplier_headers)
        except Exception as e:
            print(f"❌ Supplier fetch error: {e}")
            break

        if resp.status_code != 200:
            print(f"❌ Supplier API returned {resp.status_code}: {resp.text}")
            break

        data = resp.json().get("products", [])
        if not data:
            break

        products.extend(data)
        print(f"📥 Fetched {len(data)} products from supplier (since_id: {since_id})")
        # assume supplier products have integer id fields
        try:
            since_id = max(int(p.get("id", 0)) for p in data if p.get("id") is not None)
        except Exception:
            # fallback: break to avoid infinite loop
            break

    print(f"✅ Total supplier products fetched: {len(products)}")
    return products

# ---------- Shopify helpers ----------
def get_products_by_handle(handle):
    """Fetch a list of Shopify products matching handle (should be max 1 usually)."""
    url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products.json?handle={handle}"
    resp = request_with_retries("GET", url)
    if resp.status_code == 200:
        return resp.json().get("products", [])
    else:
        print(f"❌ Error fetching product by handle {handle}: {resp.status_code} {resp.text}")
        return []

def fetch_shopify_products_since(since_id=0, limit=250):
    """Fetch products using since_id pagination (useful for scanning vendor duplicates)."""
    products = []
    while True:
        url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products.json?limit={limit}&since_id={since_id}"
        resp = request_with_retries("GET", url)
        if resp.status_code != 200:
            print(f"❌ Error fetching shopify products: {resp.status_code} {resp.text}")
            break
        data = resp.json().get("products", [])
        if not data:
            break
        products.extend(data)
        since_id = max(p.get("id", 0) for p in data)
        if len(data) < limit:
            break
    return products

def update_product(product_id, payload):
    url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products/{product_id}.json"
    resp = request_with_retries("PUT", url, data=json.dumps(payload))
    return resp

def create_product(payload):
    url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products.json"
    resp = request_with_retries("POST", url, data=json.dumps(payload))
    return resp

def delete_product(product_id):
    url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products/{product_id}.json"
    resp = request_with_retries("DELETE", url)
    return resp

# ---------- SKU helpers ----------
def normalize_sku(sku_raw):
    if sku_raw is None:
        return None
    s = str(sku_raw).replace("#", "").strip()
    # remove trailing / leading whitespace
    return s

def base_sku_from(sku):
    # Split on whitespace and take first token; also strip trailing punctuation
    if not sku:
        return None
    base = sku.split(" ")[0].strip()
    # remove trailing punctuation like '-2' or '-4 if appended' only if obviously appended to handle? we keep it simple
    return base

def normalize_handle(base_sku):
    return base_sku.lower().strip()

# ---------- Sync logic ----------
def sync_products():
    supplier_products = fetch_supplier_products()
    if not supplier_products:
        print("⚠️ No supplier products found. Exiting.")
        return

    # Group variants by base SKU
    sku_groups = defaultdict(list)
    for product in supplier_products:
        for v in product.get("variants", []):
            if not isinstance(v, dict):
                continue
            sku_raw = v.get("sku")
            sku = normalize_sku(sku_raw)
            if not sku:
                continue
            if "(200)" in sku:
                continue
            base = base_sku_from(sku)
            if not base:
                continue
            sku_groups[base].append((product, v))

    print(f"🔁 Found {len(sku_groups)} base SKUs to process.")

    processed_handles = []
    stats = {"created": 0, "updated": 0, "failed": 0}

    for base, items in sku_groups.items():
        try:
            handle = normalize_handle(base)
            print(f"\n🔄 Syncing base SKU: {base} -> handle: {handle}")

            # Build canonical product data from first supplier product in group
            ref_product = items[0][0]
            title = ref_product.get("title", "").replace("#", "").strip() or handle
            body_html = ref_product.get("body_html", "") or ""
            product_type = ref_product.get("product_type", "") or ""
            tags = ref_product.get("tags", "") or ""
            status = ref_product.get("status", "active") or "active"

            # Build variant payloads (supplier format -> Shopify variant fields)
            supplier_variants = []
            for _, v in items:
                sku_v = normalize_sku(v.get("sku", ""))
                option1 = v.get("option1") or v.get("title") or ""
                option1 = str(option1).strip()
                variant_payload = {
                    "sku": sku_v,
                    "option1": option1,
                    "price": str(v.get("price", "0.00")),
                    # send inventory fields - Shopify may accept at variant create/update
                    "inventory_management": "shopify",
                    "inventory_policy": "deny",
                    "inventory_quantity": int(v.get("inventory_quantity", 0) or 0)
                }
                supplier_variants.append(variant_payload)

            # Always write vendor as TARGET_VENDOR
            product_payload = {
                "product": {
                    "title": title,
                    "body_html": body_html,
                    "vendor": TARGET_VENDOR,
                    "product_type": product_type,
                    "handle": handle,
                    "tags": tags,
                    "status": status,
                    # include options only when creating new product — updates will avoid changing option names
                    "options": [{"name": "Size", "values": [v.get("option1", "") for v in supplier_variants]}],
                    "variants": supplier_variants,
                    "images": ref_product.get("images", [])
                }
            }

            # Check if a product with this handle exists
            existing = get_products_by_handle(handle)
            if existing:
                shop_prod = existing[0]
                product_id = shop_prod["id"]
                print(f"🔎 Existing product found (id={product_id}) - will update existing product's variants and vendor.")

                # Build mapping of SKU -> variant id for existing product variants
                existing_variants = shop_prod.get("variants", [])
                sku_to_variant_id = {v.get("sku"): v.get("id") for v in existing_variants if v.get("sku")}

                # Prepare "update" variants payload:
                update_variants = []
                add_variants = []

                for sv in supplier_variants:
                    sku = sv.get("sku")
                    if sku in sku_to_variant_id:
                        # Update existing variant by id: include id + fields to update
                        update_variants.append({
                            "id": sku_to_variant_id[sku],
                            # do not send 'option' name changes — keep option values as-is to avoid metafield errors
                            "price": sv.get("price"),
                            "inventory_quantity": sv.get("inventory_quantity")
                        })
                    else:
                        # New variant to add
                        add_variants.append({
                            "sku": sv.get("sku"),
                            "option1": sv.get("option1"),
                            "price": sv.get("price"),
                            "inventory_management": sv.get("inventory_management"),
                            "inventory_policy": sv.get("inventory_policy"),
                            "inventory_quantity": sv.get("inventory_quantity")
                        })

                # Build a minimal update payload: update vendor and any variant updates / additions
                update_payload = {"product": {"id": product_id, "vendor": TARGET_VENDOR}}
                # Only include "variants" if we have updates or adds; for updates include variant IDs
                variants_to_send = []
                if update_variants:
                    variants_to_send.extend(update_variants)
                if add_variants:
                    variants_to_send.extend(add_variants)

                if variants_to_send:
                    update_payload["product"]["variants"] = variants_to_send

                # Avoid changing "options" when product already exists (can cause metafield conflicts)
                resp = update_product(product_id, update_payload)
                if resp.status_code in (200, 201):
                    print(f"✅ Updated product {handle} (id: {product_id}).")
                    stats["updated"] += 1
                else:
                    print(f"❌ Failed to update product {handle}: {resp.status_code} {resp.text}")
                    stats["failed"] += 1

            else:
                # Create product (handle not found)
                print(f"🆕 Creating new product for handle: {handle}")
                resp = create_product(product_payload)
                if resp.status_code in (200, 201):
                    pd = resp.json().get("product", {})
                    print(f"✅ Created product {handle} (id: {pd.get('id')}).")
                    stats["created"] += 1
                else:
                    print(f"❌ Failed to create {handle}: {resp.status_code} {resp.text}")
                    stats["failed"] += 1

            processed_handles.append(handle)

        except Exception as e:
            print(f"❌ Error handling base SKU {base}: {e}")
            stats["failed"] += 1

    print("\n📊 Sync complete. Summary:")
    print(json.dumps(stats, indent=2))

    # After sync: optional duplicate cleanup for TARGET_VENDOR
    cleanup_duplicates_by_vendor(TARGET_VENDOR)

# ---------- Duplicate cleanup ----------
def cleanup_duplicates_by_vendor(vendor):
    """
    Find duplicate handles for the specified vendor and delete all but the 'most recently updated' product.
    Prints actions; only deletes if DO_DELETE_DUPLICATES True.
    """
    print(f"\n🧹 Starting duplicate cleanup for vendor: {vendor}")
    # fetch all products (since_id pagination) and filter vendor
    all_products = fetch_shopify_products_since(0)
    # filter vendor
    vendor_products = [p for p in all_products if (p.get("vendor") or "").strip().lower() == vendor.strip().lower()]
    print(f"📥 Fetched {len(vendor_products)} products with vendor '{vendor}'")

    # group by handle
    handle_map = defaultdict(list)
    for p in vendor_products:
        handle_map[p.get("handle")].append(p)

    to_delete = []  # list of (product_id, handle) to delete
    for handle, products in handle_map.items():
        if len(products) <= 1:
            continue
        # keep the most recently updated product (updated_at)
        products_sorted = sorted(products, key=lambda x: x.get("updated_at") or "", reverse=True)
        keeper = products_sorted[0]
        deletes = products_sorted[1:]
        print(f"⚠️ Handle '{handle}' has {len(products)} products. Keeping id {keeper.get('id')}, will delete {len(deletes)} others.")
        for d in deletes:
            to_delete.append((d.get("id"), handle))

    if not to_delete:
        print("✅ No duplicates to delete.")
        return

    print(f"🗑️ Products flagged for deletion (count: {len(to_delete)}).")
    for pid, handle in to_delete:
        print(f" - {pid} (handle: {handle})")
    if DO_DELETE_DUPLICATES:
        print("⚠️ DO_DELETE_DUPLICATES is True — proceeding to delete flagged products.")
        for pid, handle in to_delete:
            try:
                resp = delete_product(pid)
                if resp.status_code in (200, 202, 204):
                    print(f"✅ Deleted product {pid} (handle: {handle})")
                else:
                    print(f"❌ Failed to delete {pid}: {resp.status_code} {resp.text}")
            except Exception as e:
                print(f"❌ Exception while deleting {pid}: {e}")
    else:
        print("ℹ️ DO_DELETE_DUPLICATES is False — not deleting. Set DO_DELETE_DUPLICATES=True to enable actual deletion.")

# ---------- Main ----------
if __name__ == "__main__":
    sync_products()
