import os
import requests
import time

# -------------------------------
# CONFIG
# -------------------------------
SUPPLIER_API_URL = os.environ.get("SUPPLIER_API_URL")
SUPPLIER_TOKEN = os.environ.get("SUPPLIER_TOKEN")

supplier_headers = {
    "X-Shopify-Access-Token": SUPPLIER_TOKEN,
    "Content-Type": "application/json"
}

if not SUPPLIER_API_URL or not SUPPLIER_TOKEN:
    raise ValueError("SUPPLIER_API_URL or SUPPLIER_TOKEN is not set!")

# -------------------------------
# STEP 1: Fetch supplier products with time delay and pagination
# -------------------------------
print("=== Fetching Supplier Products ===")

supplier_products = []
limit = 100
next_page_info = None

for attempt in range(3):  # retry 3 times if empty response
    try:
        # Add initial delay to avoid Shopify timing issues
        time.sleep(5)

        # Build URL with pagination
        url = f"{SUPPLIER_API_URL}?limit={limit}"
        if next_page_info:
            url += f"&page_info={next_page_info}"

        r = requests.get(url, headers=supplier_headers)
        r.raise_for_status()

        data = r.json()
        products_batch = data.get("products", [])
        supplier_products.extend(products_batch)
        print(f"Fetched {len(products_batch)} products this batch")

        # Check if there is a next page
        link_header = r.headers.get("Link", "")
        if 'rel="next"' in link_header:
            # Extract page_info from link header
            import re
            match = re.search(r'page_info=([^&>]+)', link_header)
            next_page_info = match.group(1) if match else None
        else:
            next_page_info = None

        if not next_page_info:  # no more pages
            break

    except Exception as e:
        print(f"Attempt {attempt+1} failed: {e}")
        time.sleep(5)  # wait before retry

print(f"\nTotal supplier products fetched: {len(supplier_products)}")
if supplier_products:
    print("Sample product title:", supplier_products[0]["title"])
