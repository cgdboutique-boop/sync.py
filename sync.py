import os
import requests
import json
from collections import defaultdict

# -------------------------------
# CONFIG
# -------------------------------
SHOPIFY_STORE = os.environ.get("SHOPIFY_STORE")  # e.g., "cgdboutique.myshopify.com"
SHOPIFY_TOKEN = os.environ.get("SHOPIFY_TOKEN")

HEADERS = {
    "X-Shopify-Access-Token": SHOPIFY_TOKEN,
    "Content-Type": "application/json"
}

# -------------------------------
# Fetch all products
# -------------------------------
def fetch_all_products():
    products = []
    url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products.json?limit=250"
    while url:
        response = requests.get(url, headers=HEADERS)
        data = response.json()
        products.extend(data.get("products", []))
        # Pagination
        link = response.headers.get("Link", "")
        if 'rel="next"' in link:
            url = link.split("<")[1].split(">")[0]
        else:
            url = None
    return products

# -------------------------------
# Delete a product
# -------------------------------
def delete_product(product_id):
    url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products/{product_id}.json"
    response = requests.delete(url, headers=HEADERS)
    return response.status_code in [200, 204]

# -------------------------------
# Update vendor name
# -------------------------------
def update_vendor(product_id, vendor_name):
    url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products/{product_id}.json"
    payload = {"product": {"id": product_id, "vendor": vendor_name}}
    response = requests.put(url, headers=HEADERS, data=json.dumps(payload))
    return response.status_code in [200, 201]

# -------------------------------
# Main logic
# -------------------------------
def main():
    print("Fetching all products from Shopify...")
    products = fetch_all_products()
    print(f"Total products fetched: {len(products)}")

    # Group products by SKU
    sku_to_products = defaultdict(list)
    for product in products:
        for variant in product.get("variants", []):
            sku = variant.get("sku")
            if sku:
                sku_to_products[sku].append(product)

    print("Checking for duplicate SKUs...")
    duplicates_count = 0
    for sku, items in sku_to_products.items():
        if len(items) > 1:
            duplicates_count += len(items) - 1
            # Keep first, delete rest
            for product_to_delete in items[1:]:
                product_id = product_to_delete["id"]
                if delete_product(product_id):
                    print(f"✅ Deleted duplicate product ID {product_id} for SKU {sku}")
                else:
                    print(f"❌ Failed to delete product ID {product_id} for SKU {sku}")

    print(f"Total duplicates deleted: {duplicates_count}")

    # Update vendor for remaining products
    print("Updating vendor for remaining products...")
    for product in products:
        update_vendor(product["id"], "CGD Kids Boutique")
        print(f"🔄 Updated vendor for product ID {product['id']}")

    print("✅ Duplicate removal and vendor update complete.")

if __name__ == "__main__":
    main()
