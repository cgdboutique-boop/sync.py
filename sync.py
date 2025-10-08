import os
import json
import requests
import time
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
# Safe request with 429 retry/backoff
# ----------------------------
def safe_request(method, url, **kwargs):
    retries = 0
    while True:
        response = requests.request(method, url, **kwargs)
        if response.status_code != 429:
            time.sleep(0.6)  # small delay to stay under 2 req/sec
            return response
        retries += 1
        wait_time = min(5, 2 ** retries)
        print(f"⚠️ Rate limit hit. Retrying in {wait_time} sec...")
        time.sleep(wait_time)

# ----------------------------
# Fetch supplier products using since_id pagination
# ----------------------------
def fetch_supplier_products(limit=250):
    products = []
    since_id = 0
    while True:
        params = {"limit": limit, "since_id": since_id}
        response = safe_request("GET", SUPPLIER_API_URL, headers=supplier_headers, params=params)
        if response.status_code != 200:
            print(f"❌ Supplier API error (since_id {since_id}): {response.text}")
            break
        data = response.json().get("products", [])
        if not data:
            break
        products.extend(data)
        print(f"📥 Fetched {len(data)} products from supplier (since_id: {since_id})")
        since_id = max([p["id"] for p in data])
    print(f"✅ Total supplier products fetched: {len(products)}")
    return products

# ----------------------------
# Check if handle exists on Shopify
# ----------------------------
def shopify_handle_exists(handle):
    url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products.json?handle={handle}"
    response = safe_request("GET", url, headers=shopify_headers)
    products = response.json().get("products", [])
    return len(products) > 0

# ----------------------------
# Main sync logic
# ----------------------------
def sync_products():
    products = fetch_supplier_products()
    sku_groups = defaultdict(list)

    # Group variants by base SKU
    for product in products:
        for v in product.get("variants", []):
            if not isinstance(v, dict):
                continue
            sku = v.get("sku")
            if not isinstance(sku, str):
                continue
            sku = sku.replace("#", "").strip()
            if "(200)" in sku or not sku:
                continue
            base_sku = sku.split(" ")[0]
            sku_groups[base_sku].append((product, v))

    synced_handles = []

    for base_sku, items in sku_groups.items():
        print(f"\n🔄 Syncing product for base SKU: {base_sku}")

        # Reference product
        product, _ = items[0]
        title = product.get("title", "").replace("#", "").strip()
        body_html = product.get("body_html", "")
        vendor = "CGD Kids Boutique"
        product_type = product.get("product_type", "")
        tags = product.get("tags", "")
        status = product.get("status", "active")
        images = product.get("images", [])

        # Clean images
        for img in images:
            if not isinstance(img, dict):
                continue
            for key in ["id", "product_id", "admin_graphql_api_id", "created_at", "updated_at"]:
                img.pop(key, None)

        # Build variants
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

        # Ensure unique handle
        handle_base = base_sku.lower().strip()
        handle = handle_base
        suffix = 1
        while shopify_handle_exists(handle):
            handle = f"{handle_base}-{suffix}"
            suffix += 1

        # Build payload
        payload = {
            "product": {
                "title": title,
                "body_html": body_html,
                "vendor": vendor,
                "product_type": product_type,
                "handle": handle,
                "tags": tags,
                "status": status,
                "options": options,
                "variants": valid_variants,
                "images": images
            }
        }

        # Check if handle exists to update
        check_url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products.json?handle={handle}"
        check_response = safe_request("GET", check_url, headers=shopify_headers)
        existing = check_response.json().get("products", [])

        if existing:
            product_id = existing[0]["id"]
            payload["product"]["id"] = product_id
            update_url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products/{product_id}.json"
            print(f"🔄 Updating existing product: {handle}")
            response = safe_request("PUT", update_url, headers=shopify_headers, data=json.dumps(payload))
        else:
            create_url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products.json"
            print(f"🆕 Creating new product: {handle}")
            response = safe_request("POST", create_url, headers=shopify_headers, data=json.dumps(payload))

        try:
            print("📦 Shopify response:")
            print(json.dumps(response.json(), indent=2))
        except Exception:
            print("❌ Failed to parse Shopify response:")
            print(response.text)

        if response.status_code in [200, 201]:
            print(f"✅ Synced: {title}")
            synced_handles.append(handle)
        else:
            print(f"❌ Failed to sync: {title} ({response.status_code})")

    # ----------------------------
    # Duplicate check report
    # ----------------------------
    print("\n📊 Duplicate Handle Check Report")
    counts = Counter(synced_handles)
    for handle, count in counts.items():
        if count > 1:
            print(f"⚠️ Duplicate detected: {handle} synced {count} times")

# ----------------------------
# Run sync
# ----------------------------
if __name__ == "__main__":
    sync_products()
