import os
import json
import requests
from collections import defaultdict, Counter

# -----------------------------------------
# Load secrets from environment
# -----------------------------------------
SHOPIFY_STORE = os.environ["SHOPIFY_STORE"]
SHOPIFY_TOKEN = os.environ["SHOPIFY_TOKEN"]
SUPPLIER_API_URL = os.environ["SUPPLIER_API_URL"]
SUPPLIER_TOKEN = os.environ["SUPPLIER_TOKEN"]

# -----------------------------------------
# Headers
# -----------------------------------------
supplier_headers = {
    "X-Shopify-Access-Token": SUPPLIER_TOKEN,
    "Accept": "application/json"
}

shopify_headers = {
    "X-Shopify-Access-Token": SHOPIFY_TOKEN,
    "Content-Type": "application/json"
}

# -----------------------------------------
# Fetch supplier products using since_id pagination
# -----------------------------------------
def fetch_supplier_products(limit=250):
    products = []
    since_id = 0

    while True:
        params = {"limit": limit, "since_id": since_id}
        response = requests.get(SUPPLIER_API_URL, headers=supplier_headers, params=params)

        if response.status_code != 200:
            print(f"❌ Supplier API error (since_id {since_id}): {response.text}")
            break

        batch = response.json().get("products", [])
        if not batch:
            break

        products.extend(batch)
        print(f"📥 Fetched {len(batch)} products (since_id: {since_id})")

        since_id = max([p["id"] for p in batch])

    print(f"✅ Total supplier products fetched: {len(products)}")
    return products

# -----------------------------------------
# Normalize SKU — Option C logic
# -----------------------------------------
def normalize_sku(sku):
    if not isinstance(sku, str):
        return None

    sku = sku.replace("#", "").strip()
    if not sku:
        return None

    # base SKU is digits only (removing spaces & parentheses)
    parts = sku.split(" ")
    base = parts[0]

    # strip off anything like "(70)" "(100)" etc
    base = base.split("(")[0].strip()

    return base

# -----------------------------------------
# Main Sync Logic
# -----------------------------------------
def sync_products():
    products = fetch_supplier_products()

    sku_groups = defaultdict(list)

    for product in products:
        for v in product.get("variants", []):

            sku = v.get("sku")
            clean = normalize_sku(sku)

            if not clean:
                continue

            sku_groups[clean].append((product, v))

    synced_handles = []

    # -----------------------------------------
    # Process grouped products
    # -----------------------------------------
    for base_sku, entries in sku_groups.items():
        print(f"\n🔄 Syncing: {base_sku}")

        product, _ = entries[0]

        title = product.get("title", "").replace("#", "").strip()
        body_html = product.get("body_html", "")

        # REQUIRED: Vendor override
        vendor = "CGD Kids Boutique"

        product_type = product.get("product_type", "")
        tags = product.get("tags", "")
        status = product.get("status", "active")

        # Prepare images
        images = product.get("images", [])
        for img in images:
            if isinstance(img, dict):
                for k in ["id", "product_id", "admin_graphql_api_id", "created_at", "updated_at"]:
                    img.pop(k, None)

        # Build variants
        variants = []
        option_values = []

        for prod, v in entries:
            sku = v.get("sku")
            if not isinstance(sku, str):
                continue

            v["sku"] = sku.replace("#", "").strip()
            v["inventory_management"] = "shopify"
            v["inventory_policy"] = "deny"
            v["price"] = v.get("price", "0.00")
            v["inventory_quantity"] = v.get("inventory_quantity", 0)
            v["option1"] = v.get("option1", "").strip()

            # Clean Shopify fields
            for k in ["id", "product_id", "inventory_item_id", "admin_graphql_api_id",
                      "created_at", "updated_at"]:
                v.pop(k, None)

            variants.append(v)
            option_values.append(v["option1"])

        options = [{"name": "Size", "values": option_values}]

        # Handle
        handle = base_sku.lower().strip()

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
                "variants": variants,
                "images": images
            }
        }

        # Check if exists
        check_url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products.json?handle={handle}"
        check = requests.get(check_url, headers=shopify_headers).json().get("products", [])

        # Update or create
        if check:
            product_id = check[0]["id"]
            payload["product"]["id"] = product_id

            url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products/{product_id}.json"
            print(f"📝 Updating: {handle}")
            response = requests.put(url, headers=shopify_headers, data=json.dumps(payload))
        else:
            url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products.json"
            print(f"➕ Creating: {handle}")
            response = requests.post(url, headers=shopify_headers, data=json.dumps(payload))

        # Log response
        try:
            print(json.dumps(response.json(), indent=2))
        except:
            print(response.text)

        if response.status_code in [200, 201]:
            synced_handles.append(handle)
            print(f"✅ Synced: {title}")
        else:
            print(f"❌ Failed: {title}")

    # -----------------------------------------
    # Detect duplicate handles
    # -----------------------------------------
    print("\n🔍 Duplicate Handle Check:")
    for h, c in Counter(synced_handles).items():
        if c > 1:
            print(f"⚠️ {h} synced {c} times!")

# -----------------------------------------
# Run Sync
# -----------------------------------------
if __name__ == "__main__":
    sync_products()
