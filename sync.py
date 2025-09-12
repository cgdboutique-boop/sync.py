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
# FETCH SUPPLIER PRODUCTS
# -------------------------------
def fetch_supplier_products(limit=100):
    url = f"{SUPPLIER_API_URL}?limit={limit}"
    r = request_with_retry("GET", url, headers=supplier_headers)
    return r.json().get("products", [])

# -------------------------------
# SYNC INVENTORY
# -------------------------------
def sync_inventory(limit=100):
    supplier_products = fetch_supplier_products(limit=limit)
    print(f"Fetched {len(supplier_products)} supplier products")

    shopify_products = request_with_retry(
        "GET", f"{SHOP_URL}/products.json?limit=250", headers=shopify_headers
    ).json().get("products", [])
    shopify_dict = {p['handle']: p for p in shopify_products}

    for p in supplier_products:
        handle = p.get("handle")
        sku = p.get("sku")
        stock = p.get("stock", 0)
        price = p.get("price")

        if not handle or not sku or stock == 0 or price is None:
            print(f"Skipping {handle or 'unknown'} (missing handle/SKU/stock/price)")
            continue

        if handle not in shopify_dict:
            print(f"Product {handle} not found in Shopify, skipping creation for now")
            continue

        product_id = shopify_dict[handle]['id']
        variant_id = shopify_dict[handle]['variants'][0]['id']

        inventory_payload = {
            "variant": {
                "id": variant_id,
                "inventory_quantity": stock,
                "price": str(price)
            }
        }

        try:
            request_with_retry(
                "PUT", f"{SHOP_URL}/variants/{variant_id}.json",
                headers=shopify_headers, json=inventory_payload
            )
            print(f"Updated inventory for {handle} (Stock: {stock}, Price: {price})")
        except Exception as e:
            print(f"Error updating {handle}: {e}")
            continue

        time.sleep(1)  # slow requests

    print("\n✅ Inventory sync completed for this batch")

# -------------------------------
# RUN SYNC (hourly-ready)
# -------------------------------
if __name__ == "__main__":
    print("=== Starting supplier inventory sync (test 100 items) ===")
    sync_inventory(limit=100)
