import requests
import os

# ------------------------------
# CONFIGURATION
# ------------------------------
SHOP_URL = "https://cgdboutique.myshopify.com/admin/api/2023-10/products.json"
SHOPIFY_TOKEN = os.getenv("SHOPIFY_TOKEN")

# Optional: Filter by supplier vendor name if you want to archive only supplier products
SUPPLIER_VENDOR = "The Brave Ones"

headers = {
    "X-Shopify-Access-Token": SHOPIFY_TOKEN,
    "Content-Type": "application/json"
}

# ------------------------------
# FETCH ALL PRODUCTS
# ------------------------------
response = requests.get(SHOP_URL, headers=headers)
if response.status_code != 200:
    print("Failed to fetch products:", response.text)
    exit(1)

products = response.json().get("products", [])
print(f"Found {len(products)} products in store.")

# ------------------------------
# ARCHIVE SUPPLIER PRODUCTS
# ------------------------------
for product in products:
    # Filter by vendor (optional)
    if SUPPLIER_VENDOR and product.get("vendor") != SUPPLIER_VENDOR:
        continue

    product_id = product["id"]
    update_url = f"https://cgdboutique.myshopify.com/admin/api/2023-10/products/{product_id}.json"
    payload = {
        "product": {
            "published": False  # Archive by unpublishing
        }
    }

    archive_response = requests.put(update_url, headers=headers, json=payload)
    if archive_response.status_code == 200:
        print(f"Archived product ID {product_id} - {product.get('title')}")
    else:
        print(f"Failed to archive product ID {product_id}:", archive_response.text)

print("Archiving complete!")
