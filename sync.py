import os
import requests

# -------------------------------
# CONFIG
# -------------------------------
SHOP_STORE = os.environ.get("SHOPIFY_STORE")
SHOPIFY_TOKEN = os.environ.get("SHOPIFY_TOKEN")
SUPPLIER_API_URL = os.environ.get("SUPPLIER_API_URL")
SUPPLIER_TOKEN = os.environ.get("SUPPLIER_TOKEN")

# Safety checks
if not SHOP_STORE or not SHOPIFY_TOKEN:
    raise ValueError("SHOPIFY_STORE or SHOPIFY_TOKEN is not set!")
if not SUPPLIER_API_URL or not SUPPLIER_TOKEN:
    raise ValueError("SUPPLIER_API_URL or SUPPLIER_TOKEN is not set!")

# Shopify setup
SHOP_URL = f"https://{SHOP_STORE}.myshopify.com/admin/api/2025-07"
shopify_headers = {
    "X-Shopify-Access-Token": SHOPIFY_TOKEN,
    "Content-Type": "application/json"
}

# Supplier setup (assuming Bearer token)
supplier_headers = {
    "Authorization": f"Bearer {SUPPLIER_TOKEN}",
    "Content-Type": "application/json"
}

# -------------------------------
# STEP 1: Test Shopify Products
# -------------------------------
print("=== Testing Shopify Store Products ===")
try:
    r = requests.get(f"{SHOP_URL}/products.json?limit=1", headers=shopify_headers)
    r.raise_for_status()
    products = r.json().get("products", [])
    print(f"Shopify products fetched: {len(products)}")
    if products:
        print("Sample product title:", products[0]["title"])
except Exception as e:
    print("Error fetching Shopify products:", e)

# -------------------------------
# STEP 2: Test Shopify Locations
# -------------------------------
print("\n=== Testing Shopify Locations ===")
try:
    r = requests.get(f"{SHOP_URL}/locations.json", headers=shopify_headers)
    r.raise_for_status()
    locations = r.json().get("locations", [])
    print(f"Shopify locations fetched: {len(locations)}")
    if locations:
        print("Sample location:", locations[0]["name"], "| ID:", locations[0]["id"])
except Exception as e:
    print("Error fetching Shopify locations:", e)

# -------------------------------
# STEP 3: Test Supplier Products
# -------------------------------
print("\n=== Testing Supplier Products ===")
try:
    r = requests.get(SUPPLIER_API_URL, headers=supplier_headers)
    r.raise_for_status()
    supplier_products = r.json().get("products", [])  # adjust key if supplier API differs
    print(f"Supplier products fetched: {len(supplier_products)}")
    if supplier_products:
        print("Sample supplier product title:", supplier_products[0]["title"])
except Exception as e:
    print("Error fetching supplier products:", e)

print("\n✅ All tests completed.")
