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
option_values = []
for v in variants:
    v["inventory_management"] = "shopify"
    v["inventory_policy"] = "deny"
    v["price"] = v.get("price", "0.00")
    v["inventory_quantity"] = v.get("inventory_quantity", 0)
    v["option1"] = v.get("option1", "").strip()
    v["sku"] = v.get("sku", "").replace("#", "").strip()
    option_values.append(v["option1"])

options = [{"name": "Size", "values": option_values}]

# Check if product exists
check_url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products.json?handle={handle}"
check_response = requests.get(check_url, headers=shopify_headers)
existing = check_response.json().get("products", [])

if existing:
    # Update product
    product_id = existing[0]["id"]
    update_payload = {
        "product": {
            "id": product_id,
            "title": title,
            "body_html": body_html,
            "tags": tags,
            "status": status,
            "options": options,
            "variants": variants,
            "images": images
        }
    }
    update_url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products/{product_id}.json"
    print("🔄 Updating product...")
    response = requests.put(update_url, headers=shopify_headers, data=json.dumps(update_payload))
    if response.status_code == 200:
        print(f"✅ Updated: {title}")
    else:
        print(f"❌ Failed to update: {title} ({response.status_code})")
        print(f"Response: {response.text}")
else:
    # Create product
    create_payload = {
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
    create_url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products.json"
    print("🆕 Creating product...")
    response = requests.post(create_url, headers=shopify_headers, data=json.dumps(create_payload))
    if response.status_code == 201:
        print(f"✅ Created: {title}")
    else:
        print(f"❌ Failed to create: {title} ({response.status_code})")
        print(f"Response: {response.text}")
