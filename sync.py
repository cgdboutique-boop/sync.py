import os
import json
import requests
from collections import defaultdict

# Load secrets from environment
SHOPIFY_STORE = os.environ["SHOPIFY_STORE"]
SHOPIFY_TOKEN = os.environ["SHOPIFY_TOKEN"]
SUPPLIER_API_URL = os.environ["SUPPLIER_API_URL"]
SUPPLIER_TOKEN = os.environ["SUPPLIER_TOKEN"]

# Headers
supplier_headers = {
    "X-Shopify-Access-Token": SUPPLIER_TOKEN,
    "Accept": "application/json"
}
shopify_headers = {
    "X-Shopify-Access-Token": SHOPIFY_TOKEN,
    "Content-Type": "application/json"
}

# Fetch supplier product data
supplier_response = requests.get(SUPPLIER_API_URL, headers=supplier_headers)
try:
    supplier_data = supplier_response.json()
except requests.exceptions.JSONDecodeError:
    print("❌ Supplier response is not valid JSON.")
    print(f"Raw response:\n{supplier_response.text[:500]}")
    exit(1)

products = supplier_data.get("products", [])
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

# Sync each SKU group
for base_sku, items in sku_groups.items():
    print(f"\n🔄 Syncing product for base SKU: {base_sku}")

    # Use first product as reference
    product, _ = items[0]
    title = product.get("title", "").replace("#", "").strip()
    body_html = product.get("body_html", "")
    vendor = product.get("vendor", "Supplier")
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
    handle = base_sku  # Use actual handle from supplier

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

    # Check if product exists
    check_url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products.json?handle={handle}"
    check_response = requests.get(check_url, headers=shopify_headers)
    existing = check_response.json().get("products", [])

    if existing:
        product_id = existing[0]["id"]
        payload["product"]["id"] = product_id
        update_url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products/{product_id}.json"
        print(f"🔄 Updating existing product: {handle}")
        response = requests.put(update_url, headers=shopify_headers, data=json.dumps(payload))
    else:
        print(f"❌ Product with handle '{handle}' not found — cannot update.")
        continue

    # Log response
    print("📦 Shopify response:")
    print(response.text)

    if response.status_code == 200:
        print(f"✅ Updated: {title}")
    else:
        print(f"❌ Failed to update: {title} ({response.status_code})")
