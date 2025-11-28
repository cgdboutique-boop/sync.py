import os
import json
import requests
import time
from collections import defaultdict

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

VENDOR_NAME = "CGD Kids Boutique"
RATE_LIMIT_DELAY = 0.5  # seconds between requests

# ----------------------------
# Fetch supplier products
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
        since_id = max([p["id"] for p in data])
        print(f"📥 Fetched {len(data)} products (since_id: {since_id})")
    print(f"✅ Total supplier products fetched: {len(products)}")
    return products

# ----------------------------
# Check if product exists by SKU or handle
# ----------------------------
def check_shopify_product(handle, sku):
    # Check by handle
    url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products.json?handle={handle}"
    resp = requests.get(url, headers=shopify_headers)
    if resp.status_code == 200:
        products = resp.json().get("products", [])
        if products:
            return products[0]  # Found by handle
    # Check by SKU
    url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products.json?sku={sku}"
    resp = requests.get(url, headers=shopify_headers)
    if resp.status_code == 200:
        products = resp.json().get("products", [])
        if products:
            return products[0]  # Found by SKU
    return None

# ----------------------------
# Sync products to Shopify
# ----------------------------
def sync_products():
    supplier_products = fetch_supplier_products()
    sku_groups = defaultdict(list)

    # Group supplier products by base SKU
    for product in supplier_products:
        for v in product.get("variants", []):
            sku = v.get("sku", "").replace("#", "").strip()
            if not sku or "(200)" in sku:
                continue
            base_sku = sku.split(" ")[0]
            sku_groups[base_sku].append((product, v))

    # Loop through grouped SKUs
    for base_sku, items in sku_groups.items():
        product, _ = items[0]
        title = product.get("title", "").replace("#", "").strip()
        body_html = product.get("body_html", "")
        product_type = product.get("product_type", "")
        tags = product.get("tags", "")
        images = product.get("images", [])
        handle = base_sku.lower().strip()

        # Clean images
        for img in images:
            for key in ["id", "product_id", "admin_graphql_api_id", "created_at", "updated_at"]:
                img.pop(key, None)

        # Build variants
        variants = []
        option_values = []
        for _, v in items:
            v_clean = {
                "sku": v.get("sku", "").replace("#", "").strip(),
                "option1": v.get("option1", "").strip(),
                "price": v.get("price", "0.00"),
                "inventory_quantity": v.get("inventory_quantity", 0),
                "inventory_management": "shopify",
                "inventory_policy": "deny",
            }
            variants.append(v_clean)
            option_values.append(v_clean["option1"])

        options = [{"name": "Size", "values": option_values}]
        payload = {
            "product": {
                "title": title,
                "body_html": body_html,
                "vendor": VENDOR_NAME,
                "product_type": product_type,
                "handle": handle,
                "tags": tags,
                "status": "active",
                "options": options,
                "variants": variants,
                "images": images,
            }
        }

        # Check existing product
        existing = check_shopify_product(handle, base_sku)
        if existing:
            payload["product"]["id"] = existing["id"]
            url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products/{existing['id']}.json"
            print(f"🔄 Updating existing product: {handle}")
            response = requests.put(url, headers=shopify_headers, data=json.dumps(payload))
        else:
            url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products.json"
            print(f"🆕 Creating new product: {handle}")
            response = requests.post(url, headers=shopify_headers, data=json.dumps(payload))

        try:
            print(json.dumps(response.json(), indent=2))
        except Exception:
            print(response.text)

        if response.status_code in [200, 201]:
            print(f"✅ Synced: {title}")
        else:
            print(f"❌ Failed to sync: {title} ({response.status_code})")
        time.sleep(RATE_LIMIT_DELAY)

# ----------------------------
# Run sync
# ----------------------------
if __name__ == "__main__":
    sync_products()
