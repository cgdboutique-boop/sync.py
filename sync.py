import os
import requests
import time
import re

# -------------------------------
# CONFIG (read from GitHub secrets)
# -------------------------------
SHOPIFY_STORE = os.environ.get("SHOPIFY_STORE")
SHOPIFY_TOKEN = os.environ.get("SHOPIFY_TOKEN")
SUPPLIER_API_URL = os.environ.get("SUPPLIER_API_URL")
SUPPLIER_TOKEN = os.environ.get("SUPPLIER_TOKEN")

if not SHOPIFY_STORE or not SHOPIFY_TOKEN:
    raise ValueError("SHOPIFY_STORE or SHOPIFY_TOKEN not set!")
if not SUPPLIER_API_URL or not SUPPLIER_TOKEN:
    raise ValueError("SUPPLIER_API_URL or SUPPLIER_TOKEN not set!")

# Shopify headers
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
# FETCH SUPPLIER PRODUCTS (100 per page with delay)
# -------------------------------
print("=== Fetching Supplier Products ===")
supplier_products = []
limit = 100
next_page_info = None

for attempt in range(3):  # retry 3 times
    try:
        time.sleep(5)  # initial delay
        url = f"{SUPPLIER_API_URL}?limit={limit}"
        if next_page_info:
            url += f"&page_info={next_page_info}"

        r = requests.get(url, headers=supplier_headers)
        print("Raw response (first 500 chars):", r.text[:500])
        r.raise_for_status()
        data = r.json()
        batch = data.get("products", [])
        supplier_products.extend(batch)
        print(f"Fetched {len(batch)} products this batch")

        # Pagination
        link_header = r.headers.get("Link", "")
        if 'rel="next"' in link_header:
            match = re.search(r'page_info=([^&>]+)', link_header)
            next_page_info = match.group(1) if match else None
        else:
            next_page_info = None

        if not next_page_info:
            break

    except Exception as e:
        print(f"Attempt {attempt+1} failed: {e}")
        time.sleep(5)

print(f"\nTotal supplier products fetched: {len(supplier_products)}")
if supplier_products:
    print("Sample supplier product title:", supplier_products[0]["title"])

# -------------------------------
# FETCH YOUR STORE PRODUCTS
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
# READY TO SYNC
# -------------------------------
print("\n=== Ready to Sync Products ===")
for product in supplier_products:
    print("-", product.get("title"), "| Handle:", product.get("handle"))

print("\n✅ Script completed.")
