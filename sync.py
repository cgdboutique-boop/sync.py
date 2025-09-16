import os
import json
import requests

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

# Filter for handle "1000106"
products = supplier_data.get("products", [])
target = [p for p in products if p.get("handle", "").strip() == "1000106"]
if not target:
    print("❌ Product with handle '1000106' not found.")
    print("🔍 Available handles:")
    for p in products:
        print("-", p.get("handle", "").strip())
    exit(1)

product = target[0]

# Extract fields
handle = product.get("handle", "").strip()
title = product.get("title", "Untitled Product").replace("#", "").strip()
body_html = product.get("body_html", "")
vendor = product.get("vendor", "Supplier")
product_type = product.get("product_type", "")
tags = product.get("tags", "")
status = product.get("status", "draft")
variants = product.get("variants", [])
images = product.get("images", [])

# Normalize variants and collect option values
valid_variants = []
option_values = []

for v in variants:
    sku = v.get("sku", "").replace("#", "").strip()
    if "(200)" in sku:
        continue  # Skip rogue variant

    v["sku"] = sku
    v["inventory_management"] = "shopify"
    v["inventory_policy"] = "deny"
    v["price"] = v.get("price", "0.00")
    v["inventory_quantity"] = v.get("inventory_quantity", 0)
    v["option1"] = v.get("option1", "").strip()

    # Strip Shopify-generated fields
    for key in ["id", "product_id", "inventory_item_id", "admin_graphql_api_id", "created_at", "updated_at"]:
        v.pop(key, None)

    valid_variants.append(v)
    option_values.append(v["option1"])

options = [{"name": "Size", "values": option_values}]

# Clean images
for img in images:
    for key in ["id", "product_id", "admin_graphql_api_id", "created_at", "updated_at"]:
        img.pop(key, None)

# Check if product exists
check_url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products.json?handle={handle}"
check_response = requests.get(check_url, headers=shopify_headers)
existing = check_response.json().get("products", [])

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

# Log payload
print("🧾 Payload being sent:")
print(json.dumps(payload, indent=2))

# Send request
if existing:
    product_id = existing[0]["id"]
    payload["product"]["id"] = product_id
    update_url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products/{product_id}.json"
    print("🔄 Updating product...")
    response = requests.put(update_url, headers=shopify_headers, data=json.dumps(payload))
else:
    create_url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products.json"
    print("🆕 Creating product...")
    response = requests.post(create_url, headers=shopify_headers, data=json.dumps(payload))

# Handle response
if response.status_code in [200, 201]:
    print(f"✅ Success: {title}")
else:
    print(f"❌ Failed to sync: {title} ({response.status_code})")
    print(f"Response: {response.text}")
