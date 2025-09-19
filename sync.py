import os
import json
import requests
import argparse
from time import sleep

# -------------------------------
# CONFIG / ENV VARIABLES
# -------------------------------
SHOPIFY_STORE = os.environ.get("SHOPIFY_STORE")
SHOPIFY_TOKEN = os.environ.get("SHOPIFY_TOKEN")
SUPPLIER_API_URL = os.environ.get("SUPPLIER_API_URL")
SUPPLIER_TOKEN = os.environ.get("SUPPLIER_TOKEN")

VENDOR_NAME = "CGD Kids Boutique"  # Vendor name to add to products
ENABLE_DELETE_DUPLICATES = True     # Set False to skip duplicates deletion

HEADERS_SHOPIFY = {
    "Content-Type": "application/json",
    "X-Shopify-Access-Token": SHOPIFY_TOKEN
}

HEADERS_SUPPLIER = {
    "Authorization": f"Bearer {SUPPLIER_TOKEN}",
    "Content-Type": "application/json"
}

# -------------------------------
# FETCH SUPPLIER PRODUCTS
# -------------------------------
def fetch_supplier_products(limit=None):
    print("Fetching products from supplier...")
    r = requests.get(SUPPLIER_API_URL, headers=HEADERS_SUPPLIER)
    r.raise_for_status()
    products = r.json().get("products", [])
    if limit:
        products = products[:limit]
    print(f"Fetched {len(products)} products.")
    return products

# -------------------------------
# DELETE DUPLICATES
# -------------------------------
def delete_duplicates():
    print("Checking for duplicate products in Shopify...")
    url = f"https://{SHOPIFY_STORE}/admin/api/2025-04/products.json?limit=250"
    r = requests.get(url, headers=HEADERS_SHOPIFY)
    r.raise_for_status()
    products = r.json().get("products", [])

    seen_titles = {}
    duplicates = []

    for prod in products:
        title = prod["title"]
        if title in seen_titles:
            duplicates.append(prod)
        else:
            seen_titles[title] = prod

    if not duplicates:
        print("No duplicates found.")
        return

    print(f"Found {len(duplicates)} duplicates. Deleting now...")
    for dup in duplicates:
        delete_url = f"https://{SHOPIFY_STORE}/admin/api/2025-04/products/{dup['id']}.json"
        r = requests.delete(delete_url, headers=HEADERS_SHOPIFY)
        if r.status_code == 200:
            print(f"Deleted duplicate: {dup['title']} (ID: {dup['id']})")
        else:
            print(f"Failed to delete {dup['title']}: {r.text}")

# -------------------------------
# CREATE / UPDATE SHOPIFY PRODUCT
# -------------------------------
def create_or_update_shopify_product(product):
    # Check if product already exists
    search_url = f"https://{SHOPIFY_STORE}/admin/api/2025-04/products.json?title={product['title']}"
    r = requests.get(search_url, headers=HEADERS_SHOPIFY)
    r.raise_for_status()
    existing_products = r.json().get("products", [])

    data = {
        "product": {
            "title": product["title"],
            "body_html": product.get("description", ""),
            "vendor": VENDOR_NAME,
            "variants": [
                {
                    "price": product.get("price", "0.00"),
                    "sku": product.get("sku", "")
                }
            ],
            "images": [{"src": img} for img in product.get("images", [])]
        }
    }

    if existing_products:
        # Update first existing product
        prod_id = existing_products[0]["id"]
        url = f"https://{SHOPIFY_STORE}/admin/api/2025-04/products/{prod_id}.json"
        r = requests.put(url, headers=HEADERS_SHOPIFY, json=data)
        if r.status_code == 200:
            print(f"Updated product: {product['title']}")
        else:
            print(f"Failed to update {product['title']}: {r.text}")
    else:
        # Create new product
        url = f"https://{SHOPIFY_STORE}/admin/api/2025-04/products.json"
        r = requests.post(url, headers=HEADERS_SHOPIFY, json=data)
        if r.status_code == 201:
            print(f"Created product: {product['title']}")
        else:
            print(f"Failed to create {product['title']}: {r.text}")

# -------------------------------
# MAIN FUNCTION
# -------------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, help="Limit number of products (for testing)")
    args = parser.parse_args()

    try:
        if ENABLE_DELETE_DUPLICATES:
            delete_duplicates()

        products = fetch_supplier_products(limit=args.limit)
        for product in products:
            create_or_update_shopify_product(product)
            sleep(0.5)  # avoid API throttling

        print("Sync completed successfully.")
    except Exception as e:
        print(f"Error during sync: {e}")

# -------------------------------
# ENTRY POINT
# -------------------------------
if __name__ == "__main__":
    main()
