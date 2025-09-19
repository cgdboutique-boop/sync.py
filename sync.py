import os
import json
import requests

# -------------------------------
# CONFIG (from environment variables / GitHub secrets)
# -------------------------------
SHOPIFY_STORE = os.environ.get("SHOPIFY_STORE")  # e.g., "yourstore.myshopify.com"
SHOPIFY_TOKEN = os.environ.get("SHOPIFY_TOKEN")

HEADERS = {
    "Content-Type": "application/json",
    "X-Shopify-Access-Token": SHOPIFY_TOKEN
}

# -------------------------------
# SAMPLE PRODUCT DATA
# -------------------------------
product_title = "Sample Product"
product_description = "<strong>Awesome product description</strong>"
product_type = "Toys"
vendor_name = "CGD Kids Boutique"
variants_list = [
    {
        "option1": "Default Title",
        "price": "99.99",
        "sku": "SKU001",
        "inventory_management": "shopify",
        "inventory_quantity": 10
    }
]
images_list = [
    {"src": "https://example.com/image1.jpg"}
]

# -------------------------------
# STEP 1: CHECK IF PRODUCT EXISTS BY TITLE
# -------------------------------
search_url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products.json?title={product_title}"
search_response = requests.get(search_url, headers=HEADERS)

if search_response.status_code == 200:
    existing_products = search_response.json().get("products", [])
    if existing_products:
        # Product exists, update it
        product_id = existing_products[0]["id"]
        print(f"🔄 Product exists. Updating Product ID: {product_id}")

        update_url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products/{product_id}.json"
        product_data = {
            "product": {
                "id": product_id,
                "title": product_title,
                "body_html": product_description,
                "vendor": vendor_name,
                "product_type": product_type,
                "variants": variants_list,
                "images": images_list
            }
        }

        update_response = requests.put(update_url, headers=HEADERS, json=product_data)
        if update_response.status_code == 200:
            print("✅ Product updated successfully!")
        else:
            print(f"❌ Failed to update product. Status: {update_response.status_code}")
            print(update_response.text)
    else:
        # Product does not exist, create it
        print("➕ Product not found. Creating new product...")
        product_data = {
            "product": {
                "title": product_title,
                "body_html": product_description,
                "vendor": vendor_name,
                "product_type": product_type,
                "variants": variants_list,
                "images": images_list
            }
        }

        create_url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products.json"
        create_response = requests.post(create_url, headers=HEADERS, json=product_data)
        if create_response.status_code == 201:
            print("✅ Product created successfully!")
        else:
            print(f"❌ Failed to create product. Status: {create_response.status_code}")
            print(create_response.text)
else:
    print(f"❌ Failed to search for product. Status: {search_response.status_code}")
    print(search_response.text)
