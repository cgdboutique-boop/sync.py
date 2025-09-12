import os
import requests
import time
import re

# -------------------------------
# CONFIG (from GitHub secrets)
# -------------------------------
SHOPIFY_STORE = os.environ.get("SHOPIFY_STORE")
SHOPIFY_TOKEN = os.environ.get("SHOPIFY_TOKEN")
SUPPLIER_API_URL = os.environ.get("SUPPLIER_API_URL")
SUPPLIER_TOKEN = os.environ.get("SUPPLIER_TOKEN")

if not SHOPIFY_STORE or not SHOPIFY_TOKEN:
    raise ValueError("SHOPIFY_STORE or SHOPIFY_TOKEN is not set!")
if not SUPPLIER_API_URL or not SUPPLIER_TOKEN:
    raise ValueError("SUPPLIER_API_URL or SUPPLIER_TOKEN is not set!")

SHOP_URL = f"https://{SHOPIFY_STORE}.myshopify.com/admin/api/2025-07"
shopify_headers = {
    "X-Shopify-Access-Token": SHOPIFY_TOKEN,
    "Content-Type": "application/json"
}
supplier_headers = {
    "X-Shopify-Access-Token": SUPPLIER_TOKEN,
    "Content-Type": "application/json"
}

# -------------------------------
# LIMIT SETTINGS
# -------------------------------
MAX_PRODUCTS_PER_RUN = 100  # stop after this many
PER_REQUEST_DELAY = 1       # seconds between create/update

# -------------------------------
# FETCH SUPPLIER PRODUCTS
# -------------------------------
print("=== Fetching Supplier Products ===")
supplier_products = []
limit = 100
next_page_info = None

while len(supplier_products) < MAX_PRODUCTS_PER_RUN:
    url = f"{SUPPLIER_API_URL}?limit={limit}"
    if next_page_info:
        url += f"&page_info={next_page_info}"

    r = requests.get(url, headers=supplier_headers)
    try:
        r.raise_for_status()
    except Exception as e:
        print("Error fetching supplier products:", e)
        break

    data = r.json()
    batch = data.get("products", [])
    supplier_products.extend(batch)
    print(f"Fetched {len(batch)} products this batch (total: {len(supplier_products)})")

    # Pagination
    link_header = r.headers.get("Link", "")
    if 'rel="next"' in link_header and len(supplier_products) < MAX_PRODUCTS_PER_RUN:
        match = re.search(r'page_info=([^&>]+)', link_header)
        next_page_info = match.group(1) if match else None
    else:
        break

    time.sleep(2)  # avoid hammering the API

print(f"\nTotal supplier products fetched this run: {len(supplier_products)}")

# -------------------------------
# FETCH YOUR STORE PRODUCTS
# -------------------------------
print("\n=== Fetching Your Shopify Store Products ===")
your_products = []
limit = 100
next_page_info = None

while True:
    url = f"{SHOP_URL}/products.json?limit={limit}"
    if next_page_info:
        url += f"&page_info={next_page_info}"

    r = requests.get(url, headers=shopify_headers)
    try:
        r.raise_for_status()
    except Exception as e:
        print("Error fetching your store products:", e)
        break

    data = r.json()
    batch = data.get("products", [])
    your_products.extend(batch)

    link_header = r.headers.get("Link", "")
    if 'rel=\"next\"' in link_header:
        match = re.search(r'page_info=([^&>]+)', link_header)
        next_page_info = match.group(1) if match else None
    else:
        break

    if len(your_products) >= 500:  # don’t fetch your whole catalog every time
        break

    time.sleep(2)

print(f"Your store products fetched: {len(your_products)}")
your_products_dict = {p['handle']: p for p in your_products}

# -------------------------------
# SYNC PRODUCTS (CREATE/UPDATE)
# -------------------------------
print("\n=== Syncing Products ===")
for supplier_product in supplier_products:
    handle = supplier_product['handle']
    product_data = {
        "product": {
            "title": supplier_product.get("title"),
            "body_html": supplier_product.get("body_html"),
            "vendor": supplier_product.get("vendor"),
            "product_type": supplier_product.get("product_type"),
            "tags": supplier_product.get("tags"),
            "handle": handle
        }
    }

    if handle in your_products_dict:
        # Update
        product_id = your_products_dict[handle]['id']
        try:
            r = requests.put(f"{SHOP_URL}/products/{product_id}.json",
                             headers=shopify_headers, json=product_data)
            r.raise_for_status()
            print(f"Updated: {handle}")
        except Exception as e:
            print(f"Error updating {handle}: {e}")
    else:
        # Create
        try:
            r = requests.post(f"{SHOP_URL}/products.json",
                              headers=shopify_headers, json=product_data)
            r.raise_for_status()
            print(f"Created: {handle}")
        except Exception as e:
            print(f"Error creating {handle}: {e}")

    time.sleep(PER_REQUEST_DELAY)

print("\n✅ Sync complete for this batch!")
