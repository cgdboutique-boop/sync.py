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

# -------------------------------
# BATCH FETCH & PROCESS
# -------------------------------
def fetch_and_process_batches():
    next_page_info = None
    total_processed = 0

    while True:
        url = f"{SUPPLIER_API_URL}?limit=100"
        if next_page_info:
            url += f"&page_info={next_page_info}"

        r = request_with_retry("GET", url, headers=supplier_headers)
        data = r.json()
        batch = data.get("products", [])

        print(f"Fetched {len(batch)} products this batch")

        if not batch:
            break

        # Fetch current Shopify products for this batch to avoid duplicates
        your_products = request_with_retry("GET", f"{SHOP_URL}/products.json?limit=250", headers=shopify_headers).json().get("products", [])
        your_products_dict = {p['handle']: p for p in your_products}
        existing_handles = set(your_products_dict.keys())

        # Process batch
        for supplier_product in batch:
            handle = supplier_product['handle']

            # Remove duplicates
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
                product_id = your_products_dict[handle]['id']
                request_with_retry("PUT", f"{SHOP_URL}/products/{product_id}.json", headers=shopify_headers, json=product_data)
                print(f"Updated: {handle}")
            else:
                request_with_retry("POST", f"{SHOP_URL}/products.json", headers=shopify_headers, json=product_data)
                print(f"Created: {handle}")
                existing_handles.add(handle)

            time.sleep(1)

        total_processed += len(batch)
        print(f"Processed batch. Total products processed so far: {total_processed}")

        # Pagination
        link_header = r.headers.get("Link", "")
        if 'rel="next"' in link_header:
            match = re.search(r'page_info=([^&>]+)', link_header)
            next_page_info = match.group(1) if match else None
        else:
            break

        time.sleep(1)

    print("\n✅ All batches processed!")

# -------------------------------
# RUN SYNC
# -------------------------------
print("=== Starting batch fetch & sync ===")
fetch_and_process_batches()
