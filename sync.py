import os
import requests
import time

# -------------------------------
# CONFIG (from GitHub secrets)
# -------------------------------
SHOPIFY_STORE = os.environ.get("SHOPIFY_STORE")
SHOPIFY_TOKEN = os.environ.get("SHOPIFY_TOKEN")
SHOPIFY_LOCATION_ID = os.environ.get("SHOPIFY_LOCATION_ID")  # you must set this in GitHub secrets!

if not SHOPIFY_STORE or not SHOPIFY_TOKEN or not SHOPIFY_LOCATION_ID:
    raise ValueError("SHOPIFY_STORE, SHOPIFY_TOKEN or SHOPIFY_LOCATION_ID is not set!")

SHOP_URL = f"https://{SHOPIFY_STORE}.myshopify.com/admin/api/2025-07"
shopify_headers = {
    "X-Shopify-Access-Token": SHOPIFY_TOKEN,
    "Content-Type": "application/json",
    "Accept": "application/json"
}

# -------------------------------
# HELPER FUNCTION
# -------------------------------
def request_with_retry(method, url, headers=None, json=None, max_retries=5):
    retry_delay = 2
    for attempt in range(max_retries):
        try:
            response = requests.request(method, url, headers=headers, json=json)
            if response.status_code in [429, 401, 422]:
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
# SYNC PRODUCT 2000133
# -------------------------------
def sync_product_2000133():
    handle = "2000133"
    title = "Ain't No Daddy Like The One I Got 2PSC Outfit #2000133"
    body_html = "Ain't No Daddy Like The One I Got 2PSC Outfit"
    vendor = "THE BRAVE ONES CHILDRENS FASHION"
    product_type = "Boys Summer"
    tags = "Boys Summer, Christmas"

    # Supplier’s stock mapping
    supplier_variants = [
        {"option1": "6-12M", "sku": "2000133-6-12M", "price": "220", "stock": 5},
        {"option1": "12-18M", "sku": "2000133-12-18M", "price": "220", "stock": 5},
        {"option1": "18-24M", "sku": "2000133-18-24M", "price": "220", "stock": 5},
    ]

    images = [
        {"src": "https://cdn.shopify.com/s/files/1/0551/4638/1501/files/6-12M_image.png", "position": 1},
        {"src": "https://cdn.shopify.com/s/files/1/0551/4638/1501/files/12-18M_image.png", "position": 2},
        {"src": "https://cdn.shopify.com/s/files/1/0551/4638/1501/files/18-24M_image.png", "position": 3},
    ]

    # Fetch products and check if this handle already exists
    r = request_with_retry("GET", f"{SHOP_URL}/products.json?limit=250", headers=shopify_headers)
    products = r.json().get("products", []) if r else []
    product = next((p for p in products if p["handle"] == handle), None)

    product_data = {
        "product": {
            "title": title,
            "body_html": body_html,
            "vendor": vendor,
            "product_type": product_type,
            "tags": tags,
            "handle": handle,
            "variants": [
                {
                    "option1": v["option1"],
                    "sku": v["sku"],
                    "price": v["price"],
                    "inventory_management": "shopify"
                }
                for v in supplier_variants
            ],
            "images": images
        }
    }

    if product:
        product_id = product["id"]
        r = request_with_retry("PUT", f"{SHOP_URL}/products/{product_id}.json",
                               headers=shopify_headers, json=product_data)
        if r:
            print(f"✅ Updated product: {handle}")
            new_product = r.json()["product"]
        else:
            print(f"❌ Failed to update product: {handle}")
            return
    else:
        r = request_with_retry("POST", f"{SHOP_URL}/products.json",
                               headers=shopify_headers, json=product_data)
        if r:
            print(f"✅ Created product: {handle}")
            new_product = r.json()["product"]
        else:
            print(f"❌ Failed to create product: {handle}")
            return

    # -------------------------------
    # Update inventory levels
    # -------------------------------
    for v in supplier_variants:
        shopify_variant = next((sv for sv in new_product["variants"] if sv["sku"] == v["sku"]), None)
        if shopify_variant:
            inventory_item_id = shopify_variant["inventory_item_id"]
            payload = {
                "location_id": SHOPIFY_LOCATION_ID,
                "inventory_item_id": inventory_item_id,
                "available": v["stock"]
            }
            r = request_with_retry("POST", f"{SHOP_URL}/inventory_levels/set.json",
                                   headers=shopify_headers, json=payload)
            if r:
                print(f"   ✅ Stock updated for {v['sku']} → {v['stock']}")
            else:
                print(f"   ❌ Failed stock update for {v['sku']}")

# -------------------------------
# RUN
# -------------------------------
if __name__ == "__main__":
    sync_product_2000133()
