import os
import requests

SHOP_URL = "https://cgdboutique.myshopify.com/admin/api/2023-10"
SHOPIFY_TOKEN = os.getenv("SHOPIFY_TOKEN")
shopify_headers = {"X-Shopify-Access-Token": SHOPIFY_TOKEN, "Content-Type": "application/json"}

# Test 1: Fetch Products
products_url = f"{SHOP_URL}/products.json?limit=1"
r = requests.get(products_url, headers=shopify_headers)
print("Products test:", r.status_code, r.text)

# Test 2: Fetch Locations
locations_url = f"{SHOP_URL}/locations.json"
r2 = requests.get(locations_url, headers=shopify_headers)
print("Locations test:", r2.status_code, r2.text)
