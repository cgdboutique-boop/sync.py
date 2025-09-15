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
def request_with_retry(method, url, headers=None, json=None, max_retries=3, backoff=5):
    """Make request and fail fast on 401"""
    for attempt in range(max_retries):
        try:
            response = requests.request(method, url, headers=headers, json=json)
            if response.status_code == 401:
                # Fail fast if token or header is invalid
                raise Exception(f"401 Unauthorized – check your token/header! URL: {url}")
            if response.status_code == 429:
                wait = int(response.headers.get("Retry-After", backoff))
                print(f"429 Rate limit hit. Waiting {wait}s...")
                time.sleep(wait)
                continue
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            print(f"Request error: {e}. Attempt {attempt+1}/{max_retries}")
            time.sleep(backoff)
    return None

# -------------------------------
# FETCH SUPPLIER PRODUCTS
# -------------------------------
def fetch_supplier_products(limit=100):
    url = f"{SUPPLIER_API_URL}?limit={limit}"
    r = request_with_retry("GET", url, headers=supplier_headers)
    if r is None:
        print("❌ Failed to fetch supplier products.")
        return []
    data = r.json()
    return data.get("products", [])

# -------------------------------
# SYNC TO SHOPIFY
# -------------------------------
def sync_products(limit=100):
    print(f"=== Starting supplier sync (limit={limit}) ===")
    supplier_products = fetch_supplier_products(limit)
    if not supplier_products:
        print("❌ No products fetched from supplier.")
        return

    shopify_products = request_with_retry("GET", f"{SHOP_URL}/products.json?limit=250", headers=shopify_headers)
    if shopify_products is None:
        print("❌ Failed to fetch Shopify products.")
        return
    shopify_products = shopify_products.json().get("products", [])
    shopify_dict = {p["handle"]: p for p in shopify_products}

    for sp in supplier_products:
        handle = sp.get("handle")
        if not handle:
            print("⚠️ Skipping product with missing handle.")
            continue

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

        if handle in shopify_dict:
            pid = shopify_dict[handle]["id"]
            r = request_with_retry("PUT", f"{SHOP_URL}/products/{pid}.json", headers=shopify_headers, json=product_data)
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

    print("✅ Supplier sync completed.")

# -------------------------------
# RUN
# -------------------------------
if __name__ == "__main__":
    sync_products(limit=100)
