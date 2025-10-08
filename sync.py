import os
import json
import time
import requests
from collections import defaultdict, Counter

# ----------------------------
# Load secrets from environment
# ----------------------------
SHOPIFY_STORE = os.environ["SHOPIFY_STORE"]
SHOPIFY_TOKEN = os.environ["SHOPIFY_TOKEN"]
SUPPLIER_API_URL = os.environ["SUPPLIER_API_URL"]
SUPPLIER_TOKEN = os.environ["SUPPLIER_TOKEN"]

# ----------------------------
# Headers
# ----------------------------
supplier_headers = {
    "X-Shopify-Access-Token": SUPPLIER_TOKEN,
    "Accept": "application/json"
}

shopify_headers = {
    "X-Shopify-Access-Token": SHOPIFY_TOKEN,
    "Content-Type": "application/json"
}

# ----------------------------
# Utility: rate limit handler
# ----------------------------
def safe_shopify_request(method, url, **kwargs):
    for attempt in range(5):
        response = requests.request(method, url, headers=shopify_headers, **kwargs)
        if response.status_code == 429:
            print("⚠️ Shopify rate limit hit — waiting 2s...")
            time.sleep(2)
            continue
        return response
    print(f"❌ Failed after retries: {url}")
    return response

# ----------------------------
# Fetch supplier products using since_id pagination
# ----------------------------
def fetch_supplier_products(limit=250):
    products = []
    since_id = 0
    while True:
        params = {"limit": limit, "since_id": since_id}
        response = requests.get(SUPPLIER_API_URL, headers=supplier_headers, params=params)
        if response.status_code != 200:
            print(f"❌ Supplier API error (since_id {since_id}): {response.text}")
            break

        data = response.json().get("products", [])
        if not data:
            break

        products.extend(data)
        print(f"📥 Fetched {len(data)} supplier products (since_id: {since_id})")
        since_id = max([p["id"] for p in data])

    print(f"✅ Total supplier products fetched: {len(products)}")
    return products

# ----------------------------
# Get Shopify products (paged)
# ----------------------------
def fetch_all_shopify_products(limit=250):
    products = []
    page_info = None
    base_url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products.json?limit={limit}"
    while True:
        url = base_url if not page_info else f"{base_url}&page_info={page_info}"
        response = safe_shopify_request("GET", url)
        if response.status_code != 200:
            print(f"❌ Error fetching Shopify products: {response.text}")
            break
        data = response.json().get("products", [])
        if not data:
            break
        products.extend(data)
        link = response.headers.get("Link", "")
        if 'rel="next"' not in link:
            break
        try:
            page_info = link.split("page_info=")[1].split(">")[0].split("&")[0]
        except Exception:
            break
    print(f"✅ Found {len(products)} total products on Shopify")
    return products

# ----------------------------
# Find Shopify product by SKU
# ----------------------------
def get_shopify_product_by_sku(sku):
    url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products.json?sku={sku}"
    response = safe_shopify_request("GET", url)
    if response.status_code == 200:
        products = response.json().get("products", [])
        return products[0] if products else None
    return None

# ----------------------------
# Delete a Shopify product by ID
# ----------------------------
def delete_shopify_product(product_id, title=""):
    url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products/{product_id}.json"
    response = safe_shopify_request("DELETE", url)
    if response.status_code == 200:
        print(f"🗑️ Deleted duplicate product: {title} ({product_id})")
    else:
        print(f"⚠️ Failed to delete {title}: {response.text}")

# ----------------------------
# Remove duplicate Shopify products
# ----------------------------
def cleanup_duplicate_shopify_products():
    print("\n🧹 Starting duplicate cleanup...")
    products = fetch_all_shopify_products()
    sku_map = defaultdict(list)

    for p in products:
        for v in p.get("variants", []):
            sku = v.get("sku")
            if sku:
                sku_map[sku].append(p)

    duplicates = {sku: plist for sku, plist in sku_map.items() if len(plist) > 1}
    print(f"📦 Found {len(duplicates)} SKUs with duplicates.")

    for sku, plist in duplicates.items():
        plist.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        keep = plist[0]
        remove = plist[1:]
        print(f"🔁 Keeping: {keep['title']} ({sku}), deleting {len(remove)} older copies...")
        for p in remove:
            delete_shopify_product(p["id"], p.get("title", ""))

    print("✅ Duplicate cleanup complete.\n")

# ----------------------------
# Main sync logic
# ----------------------------
def sync_products():
    supplier_products = fetch_supplier_products()
    if not supplier_products:
        print("⚠️ No supplier data found — stopping.")
        return

    sku_groups = defaultdict(list)

    for product in supplier_products:
        for v in product.get("variants", []):
            if not isinstance(v, dict):
                continue
            sku = str(v.get("sku", "")).strip().replace("#", "")
            if not sku or "(200)" in sku:
                continue
            base_sku = sku.split(" ")[0]
            sku_groups[base_sku].append((product, v))

    synced = []
    for base_sku, items in sku_groups.items():
        print(f"\n🔄 Syncing base SKU: {base_sku}")
        product, _ = items[0]

        title = product.get("title", "").replace("#", "").strip()
        body_html = product.get("body_html", "")
        vendor = "CGD Kids Boutique"
        product_type = product.get("product_type", "")
        tags = product.get("tags", "")
        status = product.get("status", "active")

        # Variants
        variants = []
        option_values = []
        for _, v in items:
            variant = {
                "sku": str(v.get("sku", "")).strip().replace("#", ""),
                "price": v.get("price", "0.00"),
                "option1": v.get("option1", "").strip(),
                "inventory_quantity": int(v.get("inventory_quantity", 0)),
                "inventory_management": "shopify",
                "inventory_policy": "deny",
            }
            option_values.append(variant["option1"])
            variants.append(variant)

        options = [{"name": "Size", "values": option_values}]
        handle = base_sku.lower().strip()
        images = [{"src": img["src"]} for img in product.get("images", []) if isinstance(img, dict) and img.get("src")]

        # Check for existing product
        existing = get_shopify_product_by_sku(base_sku)
        if existing:
            product_id = existing["id"]
            update_payload = {
                "product": {
                    "id": product_id,
                    "title": title,
                    "body_html": body_html,
                    "vendor": vendor,
                    "product_type": product_type,
                    "tags": tags,
                    "status": status,
                    "variants": variants,
                    "options": options,
                    "images": images,
                }
            }
            update_url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products/{product_id}.json"
            print(f"🔄 Updating existing product: {base_sku}")
            response = safe_shopify_request("PUT", update_url, data=json.dumps(update_payload))
        else:
            create_payload = {
                "product": {
                    "title": title,
                    "body_html": body_html,
                    "vendor": vendor,
                    "product_type": product_type,
                    "handle": handle,
                    "tags": tags,
                    "status": status,
                    "variants": variants,
                    "options": options,
                    "images": images,
                }
            }
            create_url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products.json"
            print(f"🆕 Creating new product: {base_sku}")
            response = safe_shopify_request("POST", create_url, data=json.dumps(create_payload))

        try:
            resp_json = response.json()
            if response.status_code in [200, 201]:
                print(f"✅ Synced successfully: {title} ({base_sku})")
                synced.append(base_sku)
            else:
                print(f"❌ Failed to sync {base_sku}: {resp_json}")
        except Exception:
            print(f"❌ Invalid response for {base_sku}: {response.text}")

    print("\n📊 Duplicate SKU Check Report")
    counts = Counter(synced)
    for sku, count in counts.items():
        if count > 1:
            print(f"⚠️ Duplicate detected for {sku}: {count} times")

    # Cleanup after sync
    cleanup_duplicate_shopify_products()

# ----------------------------
# Run
# ----------------------------
if __name__ == "__main__":
    sync_products()
