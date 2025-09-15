import os
import json
import requests

# Load secrets from environment
ACCESS_TOKEN = os.environ["SHOPIFY_ACCESS_TOKEN"]
SHOPIFY_STORE = os.environ["SHOPIFY_STORE"]

# Load supplier product data
with open("supplier_products.json", "r", encoding="utf-8") as f:
    supplier_data = json.load(f)

# Loop through each product
for product in supplier_data["products"]:
    # Map supplier product to your store's format
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

    # Send POST request to your Shopify store
    url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products.json"
    headers = {
        "Content-Type": "application/json",
        "X-Shopify-Access-Token": ACCESS_TOKEN
    }

    response = requests.post(url, headers=headers, data=json.dumps(mapped_product))

    # Handle response
    if response.status_code == 201:
        print(f"✅ Product '{product['title']}' created successfully.")
    else:
        print(f"❌ Failed to create '{product['title']}': {response.status_code}")
        print(response.text)
