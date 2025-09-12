import os
import requests
import json
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# Shopify credentials
SHOPIFY_STORE = os.getenv("SHOPIFY_STORE")  # e.g., https://yourstore.myshopify.com
SHOPIFY_TOKEN = os.getenv("SHOPIFY_TOKEN")  # Admin API token

# Supplier API credentials
SUPPLIER_API_URL = os.getenv("SUPPLIER_API_URL")
SUPPLIER_TOKEN = os.getenv("SUPPLIER_TOKEN")

# Headers
shopify_headers = {
    "Content-Type": "application/json",
    "X-Shopify-Access-Token": SHOPIFY_TOKEN
}

supplier_headers = {
    "Authorization": f"Bearer {SUPPLIER_TOKEN}"
}

def fetch_supplier_products():
    response = requests.get(SUPPLIER_API_URL, headers=supplier_headers)
    if response.status_code != 200:
        print(f"Error fetching supplier products: {response.status_code}")
        return []
    return response.json()

def product_exists(handle):
    url = f"{SHOPIFY_STORE}/admin/api/2025-07/products.json?handle={handle}"
    response = requests.get(url, headers=shopify_headers)
    if response.status_code != 200:
        print(f"Error checking existing product {handle}: {response.status_code}")
        return False
    data = response.json()
    return len(data.get("products", [])) > 0

def update_product(product_id, payload):
    url = f"{SHOPIFY_STORE}/admin/api/2025-07/products/{product_id}.json"
    response = requests.put(url, headers=shopify_headers, json={"product": payload})
    if response.status_code in [200, 201]:
        print(f"Updated product ID {product_id}")
    else:
        print(f"Error updating product ID {product_id}: {response.text}")

def create_product(payload):
    url = f"{SHOPIFY_STORE}/admin/api/2025-07/products.json"
    response = requests.post(url, headers=shopify_headers, json={"product": payload})
    if response.status_code in [200, 201]:
        print(f"Created product: {payload.get('title')}")
    else:
        print(f"Error creating product {payload.get('title')}: {response.text}")

def sync_products():
    supplier_products = fetch_supplier_products()
    if not supplier_products:
        print("No products fetched from supplier.")
        return

    for item in supplier_products:
        title = item.get("title")
        handle = item.get("handle")
        price = item.get("price")
        stock = item.get("stock", 0)

        # Skip empty or incomplete items
        if not title or not handle or price is None:
            print(f"Skipping incomplete product: {item}")
            continue

        payload = {
            "title": title,
            "handle": handle,
            "body_html": item.get("description", ""),
            "variants": [
                {
                    "price": str(price),
                    "inventory_quantity": stock,
                    "sku": item.get("sku", handle)
                }
            ],
            "images": [{"src": img} for img in item.get("images", [])] if item.get("images") else []
        }

        # Check if product exists
        if product_exists(handle):
            # Get existing product ID
            url = f"{SHOPIFY_STORE}/admin/api/2025-07/products.json?handle={handle}"
            response = requests.get(url, headers=shopify_headers)
            data = response.json()
            existing_id = data["products"][0]["id"]
            update_product(existing_id, payload)
        else:
            create_product(payload)

if __name__ == "__main__":
    sync_products()
