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
# API helper with rate-limit handling
# ----------------------------
def safe_request(method, url, headers, **kwargs):
    while True:
        response = requests.request(method, url, headers=headers, **kwargs)
        if response.status_code == 429:
            print("⚠️ Shopify rate limit hit — waiting 2s...")
            time.sleep(2)
            continue
        return response

# ----------------------------
# Fetch supplier products
# ----------------------------
def fetch_supplier_products(limit=250):
    products = []
    since_id = 0
    while True:
        params = {"limit": limit, "since_id": since_id}
        response = safe_request("GET", SUPPLIER_API_URL, supplier_headers, params=params)
        if response.status_code != 200:
            print(f"❌ Supplier API error (since_id {since_id}): {response.text}")
            break
        data = response.json().get("products", [])
        if not data:
            break
        products.extend(data)
        since_id = max([p["id"] for p in data])
        print(f"📥 Fetched {len(data)} supplier products (since_id {since_id})")
    print(f"✅ Total supplier products fetched: {len(products)}")
    return products

# ----------------------------
# Get Shopify products by vendor
# ----------------------------
def fetch_shopify_products(vendor="CGD Kids Boutique"):
    all_products = []
    page_info = None
    base_url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products.json?vendor={vendor}&limit=250"

    while True:
        url = base_url if not page_info else f"{base_url}&page_info={page_info}"
        response = safe_request("GET", url, shopify_headers)
        if response.status_code != 200:
            print(f"❌ Shopify fetch error: {response.text}")
            break
        data = response.json().get("products", [])
        if not data:
            break
        all_products.extend(data)

        if "link" in response.headers and "rel=\"next\"" in response.headers["link"]:
            links = response.headers["link"].split(",")
            next_links = [x for x in links if 'rel="next"' in x]
            if next_links:
                page_info = next_links[0].split("page_info=")[1].split(">")[0]
                continue
        break

    print(f"✅ Shopify products fetched for vendor '{vendor}': {len(all_products)}")
    return all_products

# ----------------------------
# Delete duplicates for vendor
# ----------------------------
def delete_duplicates(vendor="CGD Kids Boutique"):
    print(f"\n🧹 Checking duplicates for vendor: {vendor}")
    products = fetch_shopify_products(vendor)
    seen_handles = {}
    duplicates = []

    for product in products:
        handle = product["handle"]
        if handle not in seen_handles:
            seen_handles[handle] = product["id"]
        else:
            duplicates.append(product["id"])

    print(f"🗑️ Found {len(duplicates)} duplicates. Deleting...")
    for pid in duplicates:
        del_url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products/{pid}.json"
        resp = safe_request("DELETE", del_url, shopify_headers)
        if resp.status_code == 200:
            print(f"✅ Deleted duplicate product ID: {pid}")
        else:
            print(f"❌ Failed to delete {pid}: {resp.text}")

# ----------------------------
# Main sync logic
# ----------------------------
def sync_products():
    supplier_products = fetch_supplier_products()
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

    print(f"🛍️ Preparing to sync {len(sku_groups)} supplier SKUs")

    for base_sku, items in sku_groups.items():
        print(f"\n🔄 Syncing base SKU: {base_sku}")

        product, _ = items[0]
        title = product.get("title", "").replace("#", "").strip()
        body_html = product.get("body_html", "")
        vendor = "CGD Kids Boutique"
        tags = product.get("tags", "")
        product_type = product.get("product_type", "")
        images = product.get("images", [])
        handle = base_sku.lower().strip()

        # clean images
        for img in images:
            for key in ["id", "product_id", "admin_graphql_api_id", "created_at", "updated_at"]:
                img.pop(key, None)

        variants = []
        option_values = []
        for _, v in items:
            for key in ["id", "product_id", "inventory_item_id", "admin_graphql_api_id", "created_at", "updated_at"]:
                v.pop(key, None)
            v["inventory_management"] = "shopify"
            v["inventory_policy"] = "deny"
            v["price"] = v.get("price", "0.00")
            v["option1"] = v.get("option1", "").strip()
            option_values.append(v["option1"])
            variants.append(v)

        options = [{"name": "Size", "values": list(set(option_values))}]

        payload = {
            "product": {
                "title": title,
                "body_html": body_html,
                "vendor": vendor,
                "handle": handle,
                "tags": tags,
                "product_type": product_type,
                "status": "active",
                "options": options,
                "variants": variants,
                "images": images
            }
        }

        # Check existing Shopify product
        url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products.json?handle={handle}"
        resp = safe_request("GET", url, shopify_headers)
        existing = resp.json().get("products", [])

        if existing:
            product_id = existing[0]["id"]
            update_url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products/{product_id}.json"
            print(f"🔁 Updating existing Shopify product {base_sku}")
            resp = safe_request("PUT", update_url, shopify_headers, data=json.dumps(payload))
        else:
            create_url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products.json"
            print(f"🆕 Creating new product {base_sku}")
            resp = safe_request("POST", create_url, shopify_headers, data=json.dumps(payload))

        if resp.status_code in [200, 201]:
            print(f"✅ Synced {title}")
        else:
            print(f"❌ Failed to sync {title}: {resp.text}")

    # After syncing, clean duplicates
    delete_duplicates("CGD Kids Boutique")


# ----------------------------
# Run sync
# ----------------------------
if __name__ == "__main__":
    sync_products()
