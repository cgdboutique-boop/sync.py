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

# Fetch supplier product data
supplier_headers = {
    "X-Shopify-Access-Token": SUPPLIER_TOKEN,
    "Content-Type": "application/json"
}
supplier_response = requests.get(SUPPLIER_API_URL, headers=supplier_headers)

if supplier_response.status_code != 200:
    print(f"❌ Failed to fetch supplier data: {supplier_response.status_code}")
    print(supplier_response.text)
    exit(1)

supplier_data = supplier_response.json()
products = supplier_data.get("products", [])
if args.limit:
    products = products[:args.limit]

# Push each product to your store
for product in products:
    mapped_product = {
        "product": {
            "title": product["title"],
            "body_html": product["body_html"],
            "vendor": product["vendor"],
            "product_type": product.get("product_type", ""),
            "handle": product["handle"],
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

    # Send to your store
    url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products.json"
    headers = {
        "Content-Type": "application/json",
        "X-Shopify-Access-Token": SHOPIFY_TOKEN
    }

    response = requests.post(url, headers=headers, data=json.dumps(mapped_product))

    if response.status_code == 201:
        print(f"✅ Created: {product['title']}")
    else:
        print(f"❌ Failed: {product['title']} ({response.status_code})")
        print(response.text)
