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
# HELPER FUNCTION
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
    print(f"❌ Failed request after {max_retries} attempts: {url}")
    return None

# -------------------------------
# FETCH SUPPLIER PRODUCTS
# -------------------------------
def fetch_supplier_products(limit=100):
    url = f"{SUPPLIER_API_URL}?limit={limit}"
    r = request_with_retry("GET", url, headers=supplier_headers)
    if r is None:
        print("❌ No products fetched from supplier.")
        return []
    return r.json().get("products", [])

# -------------------------------
# SYNC PRODUCTS TO SHOPIFY
# -------------------------------
def sync_products(limit=100):
    print(f"=== Starting supplier sync (limit={limit}) ===")
    supplier_products = fetch_supplier_products(limit)
    if not supplier_products:
        return

    # Fetch current Shopify products
    r = request_with_retry("GET", f"{SHOP_URL}/products.json?limit=250", headers=shopify_headers)
    if r is None:
        print("❌ Failed to fetch Shopify products.")
        return
    shopify_products = r.json().get("products", [])
    shopify_dict = {p['handle']: p for p in shopify_products}

    for sp in supplier_products:
        sku = sp.get("sku") or ""
        handle = sp.get("handle") or ""
        title = sp.get("title") or ""

        if not handle or not sku or not title:
            print(f"Skipping product missing essential data: {handle}")
            continue

        # Build Shopify product payload
        product_data = {
            "product": {
                "title": title,
                "body_html": sp.get("body_html", ""),
                "vendor": sp.get("vendor", ""),
                "product_type": sp.get("product_type", ""),
                "tags": sp.get("tags", ""),
                "handle": handle,
                "variants": sp.get("variants", []),
                "images": sp.get("images", [])
            }
        }

        if handle in shopify_dict:
            product_id = shopify_dict[handle]['id']
            r = request_with_retry("PUT", f"{SHOP_URL}/products/{product_id}.json", headers=shopify_headers, json=product_data)
            if r:
                print(f"✅ Updated: {handle}")
            else:
                print(f"❌ Failed to update: {handle}")
        else:
            r = request_with_retry("POST", f"{SHOP_URL}/products.json", headers=shopify_headers, json=product_data)
            if r:
                print(f"✅ Created: {handle}")
            else:
                print(f"❌ Failed to create: {handle}")

        time.sleep(1)  # slow down requests

    print("\n✅ Supplier sync completed!")

# -------------------------------
# RUN SYNC
# -------------------------------
if __name__ == "__main__":
    sync_products(limit=100)
