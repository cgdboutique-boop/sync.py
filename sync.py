import os
import json
import requests
import argparse

# Parse optional --limit argument
parser = argparse.ArgumentParser()
parser.add_argument("--limit", type=int, default=None)
args = parser.parse_args()

# Load secrets from environment
SHOPIFY_STORE = os.environ["SHOPIFY_STORE"]
SHOPIFY_TOKEN = os.environ["SHOPIFY_TOKEN"]
SUPPLIER_API_URL = os.environ["SUPPLIER_API_URL"]
SUPPLIER_TOKEN = os.environ["SUPPLIER_TOKEN"]

# Headers for both stores
supplier_headers = {
    "X-Shopify-Access-Token": SUPPLIER_TOKEN,
    "Content-Type": "application/json"
}
shopify_headers = {
    "X-Shopify-Access-Token": SHOPIFY_TOKEN,
    "Content-Type": "application/json"
}

# Fetch supplier product data
supplier_response = requests.get(SUPPLIER_API_URL, headers=supplier_headers)
if supplier_response.status_code != 200:
    print(f"❌ Failed to fetch supplier data: {supplier_response.status_code}")
    print(supplier_response.text)
    exit(1)

supplier_data = supplier_response.json()
products = supplier_data.get("products", [])
if args.limit:
    products = products[:args.limit]

success_count = 0
skip_count = 0
error_count = 0

# Push each product to your store
for product in products:
    handle = product["handle"]

    # Check if product already exists
    check_url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products.json?handle={handle}"
    check_response = requests.get(check_url, headers=shopify_headers)
    existing = check_response.json().get("products", [])

    if existing:
        print(f"⚠️ Skipping existing product: {product['title']} (handle: {handle})")
        skip_count += 1
        continue

    # Map product
    mapped_product = {
        "product": {
            "title": product["title"],
            "body_html": product["body_html"],
            "vendor": product["vendor"],
            "product_type": product.get("product_type", ""),
            "handle": handle,
            "tags": product.get("tags", ""),
            "status": product.get("status", "draft"),
            "variants": [
                {
                    "sku": variant.get("sku", ""),
                    "price": variant.get("price", "0.00"),
                    "option1": variant.get("option1", "Default Title"),
                    "inventory_quantity": variant.get("inventory_quantity", 0)
                }
                for variant in product.get("variants", [])
            ],
            "images": [
                {"src": image["src"]}
                for image in product.get("images", [])
            ]
        }
    }

    # Create product
    create_url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products.json"
    response = requests.post(create_url, headers=shopify_headers, data=json.dumps(mapped_product))

    if response.status_code == 201:
        print(f"✅ Created: {product['title']}")
        success_count += 1
    else:
        print(f"❌ Failed: {product['title']} ({response.status_code})")
        print(response.text)
        error_count += 1

# Summary
print("\n📦 Sync Summary")
print(f"✅ Created: {success_count}")
print(f"⚠️ Skipped: {skip_count}")
print(f"❌ Failed: {error_count}")
