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
    """Retry API requests with exponential backoff on failure or rate limit"""
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
# FETCH SUPPLIER PRODUCTS
# -------------------------------
def fetch_supplier_products(limit=100):
    print(f"=== Starting supplier sync (limit={limit}) ===")
    url = f"{SUPPLIER_API_URL}?limit={limit}"
    r = request_with_retry("GET", url, headers=supplier_headers)
    if r is None:
        print("❌ Failed to fetch supplier products.")
        return []
    data = r.json()
    return data.get("products", [])

# -------------------------------
# CHECK SHOPIFY EXISTING PRODUCTS
# -------------------------------
def get_shopify_products():
    products = []
    url = f"{SHOP_URL}/products.json?limit=250"
    r = request_with_retry("GET", url, headers=shopify_headers)
    if r:
        products = r.json().get("products", [])
    return {p.get('variants', [{}])[0].get('sku', ''): p for p in products}

# -------------------------------
# PROCESS AND SYNC PRODUCTS
# -------------------------------
def sync_products(limit=100):
    supplier_products = fetch_supplier_products(limit=limit)
    if not supplier_products:
        print("❌ No products fetched from supplier.")
        return

    existing_products = get_shopify_products()
    total_processed = 0

    for sp in supplier_products:
        sku = sp.get("variants", [{}])[0].get("sku", "").strip()
        handle = sp.get("handle", "").strip()
        title = sp.get("title", "").strip()

        if not sku and not handle and not title:
            print("⚠️ Skipping product with no SKU, handle, or title")
            continue

        # Check for existing by SKU -> handle -> title
        existing = None
        if sku and sku in existing_products:
            existing = existing_products[sku]
        elif handle:
            existing = next((p for p in existing_products.values() if p['handle'] == handle), None)
        elif title:
            existing = next((p for p in existing_products.values() if p['title'] == title), None)

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

        if existing:
            product_id = existing["id"]
            r = request_with_retry("PUT", f"{SHOP_URL}/products/{product_id}.json", headers=shopify_headers, json=product_data)
            if r:
                print(f"Updated: {handle} (SKU: {sku})")
            else:
                print(f"❌ Failed to update: {handle} (SKU: {sku})")
        else:
            r = request_with_retry("POST", f"{SHOP_URL}/products.json", headers=shopify_headers, json=product_data)
            if r:
                print(f"Created: {handle} (SKU: {sku})")
            else:
                print(f"❌ Failed to create: {handle} (SKU: {sku})")

        total_processed += 1
        time.sleep(1)  # Slow down requests

    print(f"\n✅ Completed sync. Total products processed: {total_processed}")

# -------------------------------
# RUN SYNC
# -------------------------------
if __name__ == "__main__":
    sync_products(limit=100)  # Pull 100 products for testing
