import os
import requests
import time

# -------------------------------
# CONFIG (from GitHub secrets)
# -------------------------------
SHOPIFY_STORE = os.environ.get("SHOPIFY_STORE")
SHOPIFY_TOKEN = os.environ.get("SHOPIFY_TOKEN")

if not SHOPIFY_STORE or not SHOPIFY_TOKEN:
    raise ValueError("SHOPIFY_STORE or SHOPIFY_TOKEN is not set!")

SHOP_URL = f"https://{SHOPIFY_STORE}.myshopify.com/admin/api/2025-07"
shopify_headers = {
    "X-Shopify-Access-Token": SHOPIFY_TOKEN,
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
            if response.status_code in [429, 401]:
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
# SYNC SINGLE PRODUCT
# -------------------------------
def sync_single_product():
    handle = "2000133"
    title = "Ain't No Daddy Like The One I Got 2PSC Outfit #2000133"
    body_html = "Ain't No Daddy Like The One I Got 2PSC Outfit"
    
    variants = [
        {"option1": "6-12M", "sku": "2000133-1", "inventory_quantity": 5, "price": 220},
        {"option1": "12-18M", "sku": "2000133-2", "inventory_quantity": 5, "price": 220},
        {"option1": "18-24M", "sku": "2000133-3", "inventory_quantity": 5, "price": 220},
    ]
    
    images = [
        {"src": "https://cdn.shopify.com/s/files/1/0551/4638/1501/files/image1.jpg?v=1694862572", "position": 1},
        {"src": "https://cdn.shopify.com/s/files/1/0551/4638/1501/files/image2.jpg?v=1694862571", "position": 2},
        {"src": "https://cdn.shopify.com/s/files/1/0551/4638/1501/files/image3.jpg?v=1694862570", "position": 3},
    ]
    
    product_data = {
        "product": {
            "title": title,
            "body_html": body_html,
            "vendor": "THE BRAVE ONES CHILDRENS FASHION",
            "product_type": "Boys Summer",
            "tags": "Boys Summer, Christmas",
            "handle": handle,
            "variants": variants,
            "images": images
        }
    }

    # Check if product exists
    r = request_with_retry("GET", f"{SHOP_URL}/products.json?handle={handle}", headers=shopify_headers)
    existing_products = r.json().get("products", []) if r else []

    if existing_products:
        product_id = existing_products[0]["id"]
        r = request_with_retry("PUT", f"{SHOP_URL}/products/{product_id}.json", headers=shopify_headers, json=product_data)
        if r:
            print(f"✅ Updated product: {handle}")
        else:
            print(f"❌ Failed to update: {handle}")
    else:
        r = request_with_retry("POST", f"{SHOP_URL}/products.json", headers=shopify_headers, json=product_data)
        if r:
            print(f"✅ Created product: {handle}")
        else:
            print(f"❌ Failed to create: {handle}")

# -------------------------------
# RUN
# -------------------------------
if __name__ == "__main__":
    sync_single_product()
