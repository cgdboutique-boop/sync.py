import os
import requests
import json

# -------------------------------
# CONFIG
# -------------------------------

# Your Shopify store
SHOPIFY_STORE = os.environ.get("SHOPIFY_STORE")  # e.g., "cgdboutique"
SHOPIFY_TOKEN = os.environ.get("SHOPIFY_TOKEN")  # your store private app token

# Supplier Shopify store
SUPPLIER_API_URL = os.environ.get("SUPPLIER_API_URL")  # e.g., supplier products endpoint
SUPPLIER_TOKEN = os.environ.get("SUPPLIER_TOKEN")      # supplier private app token

# Safety checks
if not SHOPIFY_STORE or not SHOPIFY_TOKEN:
    raise ValueError("SHOPIFY_STORE or SHOPIFY_TOKEN is not set!")
if not SUPPLIER_API_URL or not SUPPLIER_TOKEN:
    raise ValueError("SUPPLIER_API_URL or SUPPLIER_TOKEN is not set!")

# Shopify URLs
SHOP_URL = f"https://{SHOPIFY_STORE}.myshopify.com/admin/api/2025-07"
shopify_headers = {
    "X-Shopify-Access-Token": SHOPIFY_TOKEN,
    "Content-Type": "application/json"
}

# Supplier headers
supplier_headers = {
    "X-Shopify-Access-Token": SUPPLIER_TOKEN,
    "Content-Type": "application/json"
}

# -------------------------------
# STEP 1: Fetch supplier products
# -------------------------------
print("=== Fetching Supplier Products ===")
try:
    r = requests.get(SUPPLIER_API_URL, headers=supplier_headers)
    r.raise_for_status()
    supplier_products = r.json().get("products", [])
    print(f"Supplier products fetched: {len(supplier_products)}")
    if supplier_products:
        print("Sample supplier product title:", supplier_products[0]["title"])
except Exception as e:
    print("Error fetching supplier products:", e)
    supplier_products = []

# -------------------------------
# STEP 2: Optional - Fetch Shopify store products
# -------------------------------
print("\n=== Fetching Your Shopify Store Products ===")
try:
    r = requests.get(f"{SHOP_URL}/products.json?limit=5", headers=shopify_headers)
    r.raise_for_status()
    your_products = r.json().get("products", [])
    print(f"Your store products fetched: {len(your_products)}")
    if your_products:
        print("Sample your store product title:", your_products[0]["title"])
except Exception as e:
    print("Error fetching your store products:", e)

# -------------------------------
# STEP 3: Optional - Sync logic
# -------------------------------
# Example: print what would be updated
print("\n=== Ready to Sync Products ===")
for product in supplier_products:
    title = product.get("title")
    handle = product.get("handle")
    print(f"- Would sync product: {title} | Handle: {handle}")

# Here you can add:
# - Compare supplier products with your store products
# - Create new products in your store
# - Update existing products (price, inventory, etc.)

print("\n✅ Script completed.")
