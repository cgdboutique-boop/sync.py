import os
import requests
import time
import re

# -------------------------------
# CONFIG
# -------------------------------
SHOPIFY_STORE = os.environ.get("SHOPIFY_STORE")
SHOPIFY_TOKEN = os.environ.get("SHOPIFY_TOKEN")
SUPPLIER_API_URL = os.environ.get("SUPPLIER_API_URL")
SUPPLIER_TOKEN = os.environ.get("SUPPLIER_TOKEN")

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
# FETCH SUPPLIER PRODUCTS
# -------------------------------
print("=== Fetching Supplier Products ===")
supplier_products = []
limit = 100
next_page_info = None

while True:
    url = f"{SUPPLIER_API_URL}?limit={limit}"
    if next_page_info:
        url += f"&page_info={next_page_info}"
    r = requests.get(url, headers=supplier_headers)
    r.raise_for_status()
    data = r.json()
    batch = data.get("products", [])
    supplier_products.extend(batch)

    # Pagination
    link_header = r.headers.get("Link", "")
    if 'rel="next"' in link_header:
        match = re.search(r'page_info=([^&>]+)', link_header)
        next_page_info = match.group(1) if match else None
    else:
        next_page_info = None

    if not next_page_info:
        break

print(f"Total supplier products fetched: {len(supplier_products)}")

# -------------------------------
# FETCH YOUR SHOPIFY STORE PRODUCTS
# -------------------------------
print("\n=== Fetching Your Shopify Store Products ===")
your_products = []
limit = 250
next_page_info = None

while True:
    url = f"{SHOP_URL}/products.json?limit={limit}"
    if next_page_info:
        url += f"&page_info={next_page_info}"
    r = requests.get(url, headers=shopify_headers)
    r.raise_for_status()
    data = r.json()
    batch = data.get("products", [])
    your_products.extend(batch)

    link_header = r.headers.get("Link", "")
    if 'rel="next"' in link_header:
        match = re.search(r'page_info=([^&>]+)', link_header)
        next_page_info = match.group(1) if match else None
    else:
        next_page_info = None

    if not next_page_info:
        break

print(f"Your store products fetched: {len(your_products)}")

# -------------------------------
# BUILD HANDLE INDEX
# -------------------------------
your_products_dict = {p['handle']: p for p in your_products}

# Detect duplicates (handles like xxx, xxx-1, xxx-2)
duplicates = {}
for p in your_products:
    base_handle = re.sub(r'-\d+$', '', p['handle'])
    duplicates.setdefault(base_handle, []).append(p)

# -------------------------------
# DELETE DUPLICATES
# -------------------------------
print("\n=== Checking for Duplicates ===")
for base, items in duplicates.items():
    if len(items) > 1:
        # keep the first one, delete the rest
        to_delete = items[1:]
        for d in to_delete:
            pid = d['id']
            try:
                r = requests.delete(f"{SHOP_URL}/products/{pid}.json", headers=shopify_headers)
                if r.status_code == 200:
                    print(f"Deleted duplicate: {d['handle']}")
            except Exception as e:
                print(f"Error deleting duplicate {d['handle']}: {e}")

# -------------------------------
# SYNC PRODUCTS
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
        # Update existing product
        product_id = your_products_dict[handle]['id']
        try:
            r = requests.put(f"{SHOP_URL}/products/{product_id}.json",
                             headers=shopify_headers, json=product_data)
            r.raise_for_status()
            print(f"Updated: {handle}")
        except Exception as e:
            print(f"Error updating {handle}: {e}")
    else:
        # Create new product
        try:
            r = requests.post(f"{SHOP_URL}/products.json",
                              headers=shopify_headers, json=product_data)
            r.raise_for_status()
            print(f"Created: {handle}")
        except Exception as e:
            print(f"Error creating {handle}: {e}")

    time.sleep(1)

print("\n✅ Sync complete without duplicates!")
