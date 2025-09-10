import os
import requests

SUPPLIER_API_URL = "https://the-brave-ones-childrens-fashion.myshopify.com/admin/api/2023-10/products.json"
SUPPLIER_TOKEN = os.getenv("SUPPLIER_TOKEN")
supplier_headers = {"X-Shopify-Access-Token": SUPPLIER_TOKEN}

supplier_response = requests.get(SUPPLIER_API_URL, headers=supplier_headers)
print("Supplier test status:", supplier_response.status_code)
print("Sample supplier data:", supplier_response.text[:500])  # first 500 chars
