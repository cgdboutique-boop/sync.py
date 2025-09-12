import os
import requests
import time

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
    return None

# -------------------------------
# FETCH SINGLE PRODUCT FROM SUPPLIER
# -------------------------------
def fetch_supplier_product(handle):
    url = f"{SUPPLIER_API_URL}?handle={handle}"
    r = request_with_retry("GET", url, headers=supplier_headers)
    if r is None:
        print(f"Failed to fetch supplier product: {handle}")
        return None
    products = r.json().get("products", [])
    return products[0] if products else None

# -------------------------------
# SYNC SINGLE PRODUCT
# -------------------------------
def sync_single_product(handle):
    print(f"=== Syncing single product: {handle} ===")
    sp = fetch_supplier_product(handle)
    if not sp:
        print(f"No product found in supplier: {handle}")
        return

    # Fetch Shopify products
    r = request_with_retry("GET", f"{SHOP_URL}/products.json?handle={handle}", headers=shopify_headers)
    if r is None:
        print("Failed to fetch Shopify product.")
        return
    shopify_products = r.json().get("products", [])
    existing = shopify_products[0] if shopify_products else None

    product_data = {
        "product": {
            "title": sp.get("title", ""),
            "body_html": sp.get("body_html", ""),
            "vendor": sp.get("vendor", ""),
            "product_type": sp.get("product_type", ""),
            "tags": sp.get("tags", ""),
            "handle": handle
        }
    }

    if existing:
        product_id = existing["id"]
        r = request_with_retry("PUT", f"{SHOP_URL}/products/{product_id}.json", headers=shopify_headers, json=product_data)
        if r:
            print(f"Updated: {handle}")
        else:
            print(f"Failed to update: {handle}")
    else:
        r = request_with_retry("POST", f"{SHOP_URL}/products.json", headers=shopify_headers, json=product_data)
        if r:
            print(f"Created: {handle}")
        else:
            print(f"Failed to create: {handle}")

    print("✅ Sync completed.")

# -------------------------------
# RUN
# -------------------------------
if __name__ == "__main__":
    sync_single_product("black-gold-sequince-dress")
