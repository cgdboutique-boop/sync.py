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

if not SHOPIFY_STORE or not SHOPIFY_TOKEN or not SUPPLIER_API_URL or not SUPPLIER_TOKEN:
    raise ValueError("One or more secrets are missing!")

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
            if response.status_code == 404:
                return None  # Product not found
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            print(f"Request error: {e}. Retrying in {retry_delay}s...")
            time.sleep(retry_delay)
            retry_delay *= 2
    raise Exception(f"Failed request after {max_retries} attempts: {url}")

def fetch_supplier_products():
    r = request_with_retry("GET", f"{SUPPLIER_API_URL}?limit=100", headers=supplier_headers)
    if not r:
        return []
    return r.json().get("products", [])

def fetch_shopify_products():
    products = []
    page_info = None
    while True:
        url = f"{SHOP_URL}/products.json?limit=250"
        if page_info:
            url += f"&page_info={page_info}"
        r = request_with_retry("GET", url, headers=shopify_headers)
        batch = r.json().get("products", [])
        products.extend(batch)
        link = r.headers.get("Link", "")
        if 'rel="next"' in link:
            match = re.search(r'page_info=([^&>]+)', link)
            page_info = match.group(1) if match else None
        else:
            break
    return {p['handle'].lower(): p for p in products}

def create_product(payload):
    if payload["variants"][0]["inventory_quantity"] <= 0:
        print(f"Skipping creation (zero stock): {payload['title']}")
        return
    r = request_with_retry("POST", f"{SHOP_URL}/products.json", headers=shopify_headers, json={"product": payload})
    if r:
        print(f"Created: {payload['title']}")

def update_product(product_id, payload):
    if payload["variants"][0]["inventory_quantity"] <= 0:
        # Delete zero-stock product
        r = request_with_retry("DELETE", f"{SHOP_URL}/products/{product_id}.json", headers=shopify_headers)
        if r is not None:
            print(f"Deleted zero-stock product ID {product_id}")
        return
    r = request_with_retry("PUT", f"{SHOP_URL}/products/{product_id}.json", headers=shopify_headers, json={"product": payload})
    if r:
        print(f"Updated: {payload['title']}")

# -------------------------------
# MAIN SYNC FUNCTION
# -------------------------------
def sync_products():
    supplier_products = fetch_supplier_products()
    if not supplier_products:
        print("No products fetched from supplier.")
        return

    shopify_products = fetch_shopify_products()

    for item in supplier_products:
        title = item.get("title")
        handle = (item.get("handle") or "").strip().lower()
        price = item.get("price")
        stock = item.get("stock", 0)

        # Skip incomplete or zero-stock items
        if not title or not handle or price is None or stock <= 0:
            print(f"Skipping product: {title} (handle: {handle})")
            continue

        payload = {
            "title": title,
            "handle": handle,
            "body_html": item.get("body_html") or item.get("description", ""),
            "vendor": item.get("vendor", ""),
            "product_type": item.get("product_type", ""),
            "tags": item.get("tags", ""),
            "variants": [
                {
                    "price": str(price),
                    "inventory_quantity": stock,
                    "sku": item.get("sku", handle)
                }
            ],
            "images": [{"src": img} for img in item.get("images", [])] if item.get("images") else []
        }

        if handle in shopify_products:
            product_id = shopify_products[handle]["id"]
            update_product(product_id, payload)
        else:
            create_product(payload)

# -------------------------------
# RUN
# -------------------------------
print("=== Starting supplier sync ===")
sync_products()
print("✅ Supplier sync complete!")
