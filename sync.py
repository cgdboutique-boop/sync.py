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
    "Authorization": f"Bearer {SUPPLIER_TOKEN}",
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
            if response.status_code in [401, 429]:
                wait = int(response.headers.get("Retry-After", retry_delay))
                print(f"{response.status_code} error. Retrying in {wait}s...")
                time.sleep(wait)
                retry_delay *= 2
                continue
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            print(f"Request error: {e}. Retrying in {retry_delay}s...")
            time.sleep(retry_delay)
            retry_delay *= 2
    return None

# -------------------------------
# FETCH SUPPLIER PRODUCTS (batch)
# -------------------------------
def fetch_supplier_products(limit=100, page_info=None):
    url = f"{SUPPLIER_API_URL}?limit={limit}"
    if page_info:
        url += f"&page_info={page_info}"

    r = request_with_retry("GET", url, headers=supplier_headers)
    if not r:
        print("❌ Failed to fetch supplier products.")
        return []

    data = r.json()
    return data.get("products", []), data.get("next_page_info")

# -------------------------------
# FETCH SHOPIFY PRODUCTS
# -------------------------------
def fetch_shopify_products():
    r = request_with_retry("GET", f"{SHOP_URL}/products.json?limit=250", headers=shopify_headers)
    if not r:
        return []
    return r.json().get("products", [])

# -------------------------------
# SYNC PRODUCTS
# -------------------------------
def sync_products(limit=100):
    print(f"=== Starting supplier sync (limit={limit}) ===")

    next_page = None
    total_processed = 0

    shopify_products = fetch_shopify_products()
    shopify_dict_by_handle = {p["handle"]: p for p in shopify_products}

    while True:
        supplier_batch, next_page = fetch_supplier_products(limit=limit, page_info=next_page)
        if not supplier_batch:
            break

        for sp in supplier_batch:
            sku = sp.get("sku")
            handle = sp.get("handle")
            title = sp.get("title")

            if not (sku or handle or title):
                print(f"Skipping product with missing SKU, handle, and title.")
                continue

            key = sku or handle or title

            existing = None
            if handle and handle in shopify_dict_by_handle:
                existing = shopify_dict_by_handle[handle]

            product_data = {
                "product": {
                    "title": title or "",
                    "body_html": sp.get("body_html", ""),
                    "vendor": sp.get("vendor", ""),
                    "product_type": sp.get("product_type", ""),
                    "tags": sp.get("tags", ""),
                    "handle": handle or key
                }
            }

            if existing:
                product_id = existing["id"]
                r = request_with_retry("PUT", f"{SHOP_URL}/products/{product_id}.json", headers=shopify_headers, json=product_data)
                if r:
                    print(f"Updated: {key}")
                else:
                    print(f"Failed to update: {key}")
            else:
                r = request_with_retry("POST", f"{SHOP_URL}/products.json", headers=shopify_headers, json=product_data)
                if r:
                    print(f"Created: {key}")
                else:
                    print(f"Failed to create: {key}")

            time.sleep(1)  # slow down requests

        total_processed += len(supplier_batch)
        print(f"Processed batch. Total products processed: {total_processed}")

        if not next_page:
            break

    print("\n✅ All supplier products synced!")

# -------------------------------
# RUN
# -------------------------------
if __name__ == "__main__":
    sync_products(limit=100)
