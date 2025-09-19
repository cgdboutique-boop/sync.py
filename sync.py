import os
import json
import requests
import time

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
# You can loop through multiple products here if needed
product_title = "Sample Product"
product_description = "<strong>Awesome product description</strong>"
product_type = "Toys"
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
# CREATE/UPDATE PRODUCT PAYLOAD
# -------------------------------
product_data = {
    "title": product_title,
    "body_html": product_description,
    "vendor": "CGD Kids Boutique",  # <-- vendor added
    "product_type": product_type,
    "variants": variants_list,
    "images": images_list
}

shopify_url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products.json"

# -------------------------------
# MAKE THE REQUEST
# -------------------------------
response = requests.post(shopify_url, headers=HEADERS, json={"product": product_data})

if response.status_code == 201:
    print("✅ Product created successfully!")
    product_response = response.json()
    print(json.dumps(product_response, indent=2))
else:
    print(f"❌ Failed to create product. Status Code: {response.status_code}")
    print(response.text)
