import json
import requests
from collections import defaultdict, Counter

# ----------------------------

# Load secrets from environment

# ----------------------------

SHOPIFY_STORE = os.environ["SHOPIFY_STORE"]
SHOPIFY_TOKEN = os.environ["SHOPIFY_TOKEN"]
SUPPLIER_API_URL = os.environ["SUPPLIER_API_URL"]
SUPPLIER_TOKEN = os.environ["SUPPLIER_TOKEN"]

# ----------------------------

# Headers

# ----------------------------

supplier_headers = {
"X-Shopify-Access-Token": SUPPLIER_TOKEN,
"Accept": "application/json"
}

shopify_headers = {
"X-Shopify-Access-Token": SHOPIFY_TOKEN,
"Content-Type": "application/json"
}

# ----------------------------

# Fetch supplier products using since_id pagination

# ----------------------------

def fetch_supplier_products(limit=250):
products = []
since_id = 0
while True:
params = {"limit": limit, "since_id": since_id}
response = requests.get(SUPPLIER_API_URL, headers=supplier_headers, params=params)
if response.status_code != 200:
print(f"❌ Supplier API error (since_id {since_id}): {response.text}")
break
data = response.json().get("products", [])
if not data:
break
products.extend(data)
print(f"📥
