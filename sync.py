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

# Two possible header styles for supplier
supplier_headers_shopify = {
    "X-Shopify-Access-Token": SUPPLIER_TOKEN,
    "Content-Type": "application/json"
}
supplier_headers_bearer = {
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
# TRY SUPPLIER AUTH
# -------------------------------
def fetch_supplier_products(limit=100):
    url = f"{SUPPLIER_API_URL}?limit={limit}"

    # Try Shopify-style headers first
    print("🔎 Trying supplier with Shopify-style headers...")
    r = request_with_retry("GET", url, headers=supplier_headers_shopify)
    if r and r.status_code == 200:
        print("✅ Supplier auth worked with X-Shopify-Access-Token")
        return r.json().get("products", [])

    # Try Bearer-style headers
    print("🔎 Shopify headers failed. Trying Bearer token...")
    r = request_with_retry("GET", url, headers=supplier_headers_bearer)
    if r and r.status_code == 200:
        print("✅ Supplier auth worked with Bearer token")
        return r.json().get("products", [])

    print("❌ Both auth methods failed for supplier API.")
    return []

# -------------------------------
# SYNC PRODUCTS
# -------------------------------
def sync_products(limit=100):
    print(f"=== Starting supplier sync (limit={limit}) ===")
    supplier_products = fetch_supplier_products(limit=limit)
    if not supplier_products:
        print("❌ No products fetched from supplier.")
        return

    # Fetch Shopify products
    shopify_products = request_with_retry("GET", f"{SHOP_URL}/products.json?limit=250", headers=shopify_headers)
    if not shopify_products:
        print("❌ Failed to fetch Shopify products.")
        return
    your_products = shopify_products.json().get("products", [])
    existing_handles = {p['handle']: p for p in your_products}

    # Process supplier products
    for sp in supplier_products:
        handle = sp.get("handle") or f"sku-{sp.get('sku', 'unknown')}"
        if not handle:
            print("⚠️ Skipping product with no handle or sku")
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

        if handle in existing_handles:
            product_id = existing_handles[handle]["id"]
            request_with_retry("PUT", f"{SHOP_URL}/products/{product_id}.json", headers=shopify_headers, json=product_data)
            print(f"🔄 Updated: {handle}")
        else:
            request_with_retry("POST", f"{SHOP_URL}/products.json", headers=shopify_headers, json=product_data)
            print(f"✨ Created: {handle}")

        time.sleep(1)

    print("\n✅ Sync completed.")

# -------------------------------
# RUN
# -------------------------------
if __name__ == "__main__":
    sync_products(limit=100)
