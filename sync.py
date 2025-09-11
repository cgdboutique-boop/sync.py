import requests
import os

# Environment variables for security
SHOPIFY_STORE = "the-brave-ones-childrens-fashion.myshopify.com"
SHOPIFY_TOKEN = os.getenv("SUPPLIER_TOKEN")  # Ensure this environment variable is set

# Construct the API URL
url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products.json"

# Set the headers with the API token
headers = {
    "X-Shopify-Access-Token": SHOPIFY_TOKEN
}

# Send the GET request to fetch products
response = requests.get(url, headers=headers)

# Check if the request was successful
if response.status_code == 200:
    products = response.json().get("products", [])
    print(f"Fetched {len(products)} products.")
    for product in products:
        print(f"Product ID: {product['id']}, Title: {product['title']}")
else:
    print(f"Failed to fetch products. Status Code: {response.status_code}")
    print(response.text)
