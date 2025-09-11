import os
import requests

# Load secrets from environment
SUPPLIER_TOKEN = os.environ.get("SUPPLIER_TOKEN")
SHOPIFY_STORE = os.environ.get("SHOPIFY_STORE")
SHOPIFY_TOKEN = os.environ.get("SHOPIFY_TOKEN")

# Supplier API URL
SUPPLIER_API_URL = "https://supplier.com/api/products"  # Replace with actual endpoint

# Shopify API URL
SHOPIFY_API_URL = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products.json"

# Step 1: Fetch products from supplier
supplier_headers = {"Authorization": f"Bearer {SUPPLIER_TOKEN}"}
response = requests.get(SUPPLIER_API_URL, headers=supplier_headers)

if response.status_code != 200:
    print("Failed to fetch supplier products:", response.status_code, response.text)
    exit(1)

supplier_products = response.json()

# Step 2: Loop through supplier products and push to Shopify
shopify_headers = {
    "Content-Type": "application/json",
    "X-Shopify-Access-Token": SHOPIFY_TOKEN
}

for product in supplier_products:
    shopify_product = {
        "product": {
            "title": product.get("name", "No Name"),
            "body_html": product.get("description", ""),
            "variants": [
                {
                    "sku": variant.get("sku", ""),
                    "price": variant.get("price", "0.00"),
                    "inventory_quantity": variant.get("stock", 0)
                } for variant in product.get("variants", [])
            ]
        }
    }

    r = requests.post(SHOPIFY_API_URL, headers=shopify_headers, json=shopify_product)

    if r.status_code in [200, 201]:
        print(f"Successfully synced: {product.get('name')}")
    else:
        print(f"Failed to sync: {product.get('name')}", r.status_code, r.text)
