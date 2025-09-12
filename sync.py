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
    data = r.json()
    return data.get("products", [])

# -------------------------------
# SYNC FUNCTION
# -------------------------------
def sync_products(limit=100):
    supplier_products = fetch_supplier_products(limit=limit)
    if not supplier_products:
        print("No products fetched from supplier.")
        return

    # Fetch existing Shopify products
    existing_products = request_with_retry("GET", f"{SHOP_URL}/products.json?limit=250", headers=shopify_headers).json().get("products", [])
    existing_dict = {p['handle']: p for p in existing_products}

    for item in supplier_products:
        handle = item.get("handle")
        stock = item.get("stock", 0)

        # Skip products with zero stock
        if stock == 0:
            print(f"Skipping zero-stock product: {handle}")
            continue

        payload = {
            "product": {
                "title": item.get("title"),
                "body_html": item.get("description", ""),
                "vendor": item.get("vendor", ""),
                "product_type": item.get("product_type", ""),
                "tags": item.get("tags", ""),
                "handle": handle,
                "variants": [{
                    "price": str(item.get("price", "0.00")),
                    "inventory_quantity": stock,
                    "sku": item.get("sku", handle)
                }],
                "images": [{"src": img} for img in item.get("images", [])] if item.get("images") else []
            }
        }

        if handle in existing_dict:
            product_id = existing_dict[handle]['id']
            request_with_retry("PUT", f"{SHOP_URL}/products/{product_id}.json", headers=shopify_headers, json=payload)
            print(f"Updated: {handle}")
        else:
            request_with_retry("POST", f"{SHOP_URL}/products.json", headers=shopify_headers, json=payload)
            print(f"Created: {handle}")

        time.sleep(1)  # avoid hitting rate limits

# -------------------------------
# RUN SYNC
# -------------------------------
print("=== Starting supplier sync (test 100 items) ===")
sync_products(limit=100)
print("✅ Sync complete")
