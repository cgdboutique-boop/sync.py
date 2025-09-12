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
# HELPER FUNCTIONS
# -------------------------------
def request_with_retry(method, url, headers=None, json=None, max_retries=5):
    retry_delay = 2
    for attempt in range(max_retries):
        try:
            response = requests.request(method, url, headers=headers, json=json)
            if response.status_code == 429:  # Too Many Requests
                retry_after = int(response.headers.get("Retry-After", retry_delay))
                print(f"429 Rate limit hit. Sleeping {retry_after}s...")
                time.sleep(retry_after)
                continue
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            print(f"Request error: {e}. Retrying in {retry_delay}s...")
            time.sleep(retry_delay)
            retry_delay *= 2
    raise Exception(f"Failed request after {max_retries} attempts: {url}")

def fetch_all_products(url, headers):
    all_products = []
    limit = 100
    next_page_info = None

    while True:
        fetch_url = f"{url}?limit={limit}"
        if next_page_info:
            fetch_url += f"&page_info={next_page_info}"

        r = request_with_retry("GET", fetch_url, headers=headers)
        data = r.json()
        batch = data.get("products", [])
        all_products.extend(batch)
        print(f"Fetched {len(batch)} products this batch (total: {len(all_products)})")

        link_header = r.headers.get("Link", "")
        if 'rel="next"' in link_header:
            match = re.search(r'page_info=([^&>]+)', link_header)
            next_page_info = match.group(1) if match else None
        else:
            next_page_info = None

        if not next_page_info:
            break

        time.sleep(1)  # small delay to avoid rate limit

    return all_products

# -------------------------------
# FETCH PRODUCTS
# -------------------------------
print("=== Fetching Supplier Products ===")
supplier_products = fetch_all_products(SUPPLIER_API_URL, supplier_headers)
print(f"Total supplier products fetched: {len(supplier_products)}")

print("\n=== Fetching Your Shopify Store Products ===")
your_products = fetch_all_products(f"{SHOP_URL}/products.json", shopify_headers)
your_products_dict = {p['handle']: p for p in your_products}
print(f"Your store products fetched: {len(your_products)}")

# -------------------------------
# SYNC PRODUCTS
# -------------------------------
print("\n=== Syncing Products ===")
existing_handles = set(your_products_dict.keys())

for supplier_product in supplier_products:
    handle = supplier_product['handle']

    # Remove any duplicates in the store (same handle)
    duplicates = [p for p in your_products if p['handle'] == handle and p['id'] != your_products_dict.get(handle, {}).get('id')]
    for dup in duplicates:
        print(f"Deleting duplicate: {dup['handle']} ({dup['id']})")
        request_with_retry("DELETE", f"{SHOP_URL}/products/{dup['id']}.json", headers=shopify_headers)
        time.sleep(1)

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

    if handle in existing_handles:
        # Update existing product
        product_id = your_products_dict[handle]['id']
        request_with_retry("PUT", f"{SHOP_URL}/products/{product_id}.json", headers=shopify_headers, json=product_data)
        print(f"Updated: {handle}")
    else:
        # Create new product
        request_with_retry("POST", f"{SHOP_URL}/products.json", headers=shopify_headers, json=product_data)
        print(f"Created: {handle}")
        existing_handles.add(handle)

    time.sleep(1)  # small delay to avoid hitting rate limits

print("\n✅ Sync complete!")
