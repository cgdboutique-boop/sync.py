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
# Fetch all Shopify products
# ----------------------------
def fetch_all_shopify_products():
    products = []
    url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products.json?limit=250"
    while url:
        response = requests.get(url, headers=shopify_headers)
        if response.status_code != 200:
            print(f"❌ Error fetching Shopify products: {response.text}")
            break
        data = response.json().get("products", [])
        products.extend(data)
        link_header = response.headers.get("Link")
        next_url = None
        if link_header:
            parts = link_header.split(",")
            for part in parts:
                if 'rel="next"' in part:
                    next_url = part.split("<")[1].split(">")[0]
                    break
        url = next_url
        if url:
            time.sleep(RATE_LIMIT_DELAY)
    print(f"✅ Total Shopify products fetched: {len(products)}")
    return products

# ----------------------------
# Sync supplier products to Shopify
# ----------------------------
def sync_products():
    supplier_products = fetch_supplier_products()
    shopify_products = fetch_all_shopify_products()
    shopify_products = [p for p in shopify_products if p.get("vendor") == VENDOR_NAME]

    shopify_sku_map = {}
    shopify_handle_map = {}
    for p in shopify_products:
        for v in p.get("variants", []):
            sku = v.get("sku", "").strip()
            if sku:
                shopify_sku_map[sku] = p
        handle = p.get("handle")
        if handle:
            shopify_handle_map[handle] = p

    sku_groups = defaultdict(list)
    for product in supplier_products:
        for v in product.get("variants", []):
            sku = v.get("sku", "")
            if not sku:
                continue
            sku = sku.replace("#", "").strip()
            if "(200)" in sku:
                continue
            base_sku = sku.split(" ")[0]
            sku_groups[base_sku].append((product, v))

    synced_handles = []

    for base_sku, items in sku_groups.items():
        print(f"\n🔄 Syncing base SKU: {base_sku}")
        product, _ = items[0]
        title = product.get("title", "").replace("#", "").strip()
        body_html = product.get("body_html", "")
        product_type = product.get("product_type", "")
        tags = product.get("tags", "")
        status = product.get("status", "active")
        images = product.get("images", [])
        for img in images:
            for key in ["id", "product_id", "admin_graphql_api_id", "created_at", "updated_at"]:
                img.pop(key, None)

        valid_variants = []
        option_values = []
        for _, v in items:
            v["sku"] = v.get("sku", "").replace("#", "").strip()
            v["inventory_management"] = "shopify"
            v["inventory_policy"] = "deny"
            v["price"] = v.get("price", "0.00")
            v["inventory_quantity"] = v.get("inventory_quantity", 0)
            v["option1"] = v.get("option1", "").strip()
            for key in ["id", "product_id", "inventory_item_id", "admin_graphql_api_id", "created_at", "updated_at"]:
                v.pop(key, None)
            valid_variants.append(v)
            option_values.append(v["option1"])

        options = [{"name": "Size", "values": option_values}]
        handle = base_sku.lower().strip()
        payload = {
            "product": {
                "title": title,
                "body_html": body_html,
                "vendor": VENDOR_NAME,
                "product_type": product_type,
                "handle": handle,
                "tags": tags,
                "status": status,
                "options": options,
                "variants": valid_variants,
                "images": images
            }
        }

        existing_product = shopify_sku_map.get(base_sku) or shopify_handle_map.get(handle)

        if existing_product:
            product_id = existing_product["id"]
            payload["product"]["id"] = product_id
            update_url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products/{product_id}.json"
            print(f"🔄 Updating existing product: {handle}")
            response = requests.put(update_url, headers=shopify_headers, data=json.dumps(payload))
        else:
            create_url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products.json"
            print(f"🆕 Creating new product: {handle}")
            response = requests.post(create_url, headers=shopify_headers, data=json.dumps(payload))

        try:
            print(json.dumps(response.json(), indent=2))
        except:
            print(response.text)

        if response.status_code in [200, 201]:
            synced_handles.append(handle)
            print(f"✅ Synced: {title}")
        else:
            print(f"❌ Failed to sync: {title} ({response.status_code})")

        time.sleep(RATE_LIMIT_DELAY)

    cleanup_duplicates(VENDOR_NAME)

# ----------------------------
# Delete duplicates for this vendor
# ----------------------------
def cleanup_duplicates(vendor_name):
    print(f"\n🔍 Cleaning duplicates for vendor: {vendor_name}")
    products = fetch_all_shopify_products()
    products = [p for p in products if p.get("vendor") == vendor_name]

    sku_map = defaultdict(list)
    handle_map = defaultdict(list)

    for p in products:
        for v in p.get("variants", []):
            sku = v.get("sku", "").strip()
            if sku:
                sku_map[sku].append(p)
        handle = p.get("handle")
        if handle:
            handle_map[handle].append(p)

    def delete_older(items, key_name):
        for key, prods in items.items():
            if len(prods) <= 1:
                continue
            prods_sorted = sorted(prods, key=lambda x: x.get("updated_at", ""), reverse=True)
            keep = prods_sorted[0]
            delete_list = prods_sorted[1:]
            for d in delete_list:
                product_id = d["id"]
                del_url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products/{product_id}.json"
                response = requests.delete(del_url, headers=shopify_headers)
                if response.status_code in [200, 204]:
                    print(f"🗑️ Deleted duplicate {key_name}: {key} (product id {product_id})")
                else:
                    print(f"❌ Failed to delete {key_name}: {key} (product id {product_id}) - {response.text}")
                time.sleep(RATE_LIMIT_DELAY)

    delete_older(sku_map, "SKU")
    delete_older(handle_map, "Handle")

# ----------------------------
# Run sync
# ----------------------------
if __name__ == "__main__":
    sync_products()
