import os
import requests

# Load secrets from environment (GitHub Actions will provide these)
SUPPLIER_TOKEN = os.environ["SUPPLIER_TOKEN"]
SHOPIFY_STORE = os.environ["SHOPIFY_STORE"]
SHOPIFY_TOKEN = os.environ["SHOPIFY_TOKEN"]

# Supplier API URL (replace with your supplier's endpoint)
SUPPLIER_API_URL = "https://supplier.com/api/products"

# Fetch products from supplier
supplier_headers = {"Authorization": f"Bearer {SUPPLIER_TOKEN}"}
response = requests.get(SUPPLIER_API_URL, headers=supplier_headers)
supplier_products = response.json()

# Shopify API URL
SHOPIFY_API_URL = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products.json"
shopify_headers = {
    "Content-Type": "application/json",
    "X-Shopify-Access-Token": SHOPIFY_TOKEN
}

# Sync products to Shopify
for product in supplier_products:
    shopify_product = {
        "product": {
            "title": product["name"],
            "body_html": product.get("description", ""),
            "variants": [
                {
                    "price": v["price"],
                    "sku": v["sku"],
                    "inventory_quantity": v.get("stock", 0)
                } for v in product.get("variants", [])
            ]
        }
    }
    r = requests.post(SHOPIFY_API_URL, headers=shopify_headers, json=shopify_product)
    print(r.status_code, r.json())

