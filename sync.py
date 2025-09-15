import os
import requests
import time

# -------------------------------
# CONFIG (from GitHub secrets)
# -------------------------------
SHOPIFY_STORE = os.environ.get("SHOPIFY_STORE")
SHOPIFY_TOKEN = os.environ.get("SHOPIFY_TOKEN")
LOCATION_ID = os.environ.get("SHOPIFY_LOCATION_ID")  # Required for inventory updates

if not SHOPIFY_STORE or not SHOPIFY_TOKEN or not LOCATION_ID:
    raise ValueError("SHOPIFY_STORE, SHOPIFY_TOKEN, or SHOPIFY_LOCATION_ID is not set!")

SHOP_URL = f"https://{SHOPIFY_STORE}.myshopify.com/admin/api/2025-07"
shopify_headers = {
    "X-Shopify-Access-Token": SHOPIFY_TOKEN,
    "Content-Type": "application/json"
}

# -------------------------------
# HELPER FUNCTION WITH RETRY
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
# SYNC SINGLE PRODUCT
# -------------------------------
def sync_product_2000133():
    handle = "2000133"
    title = "Ain't No Daddy Like The One I Got 2PSC Outfit #2000133"
    body_html = "Ain't No Daddy Like The One I Got 2PSC Outfit"
    vendor = "THE BRAVE ONES CHILDRENS FASHION"
    product_type = "Boys Summer"
    tags = "Boys Summer, Christmas"

    # Variant data with correct Shopify variant IDs
    variants_data = [
        {"id": 44481333362934, "option1": "6-12M", "sku": "2000133", "inventory_quantity": 5, "price": 220},
        {"id": 44481333395702, "option1": "12-18M", "sku": "2000133", "inventory_quantity": 5, "price": 220},
        {"id": 44481333428470, "option1": "18-24M", "sku": "2000133", "inventory_quantity": 5, "price": 220}
    ]

    # Images mapped to variant IDs
    images = [
        {"src": "https://cdn.shopify.com/s/files/1/0551/4638/1501/files/6-12M_image.png", "position": 1, "variant_ids": [44481333362934]},
        {"src": "https://cdn.shopify.com/s/files/1/0551/4638/1501/files/12-18M_image.png", "position": 2, "variant_ids": [44481333395702]},
        {"src": "https://cdn.shopify.com/s/files/1/0551/4638/1501/files/18-24M_image.png", "position": 3, "variant_ids": [44481333428470]}
    ]

    # -------------------------------
    # 1️⃣ Get existing product
    # -------------------------------
    r = request_with_retry("GET", f"{SHOP_URL}/products.json?handle={handle}", headers=shopify_headers)
    if not r:
        print("❌ Failed to fetch product")
        return
    existing_products = r.json().get("products", [])

    product_data = {
        "product": {
            "title": title,
            "body_html": body_html,
            "vendor": vendor,
            "product_type": product_type,
            "tags": tags,
            "handle": handle,
            "images": images
        }
    }

    # -------------------------------
    # 2️⃣ Create or update product
    # -------------------------------
    if existing_products:
        product_id = existing_products[0]["id"]
        r = request_with_retry("PUT", f"{SHOP_URL}/products/{product_id}.json", headers=shopify_headers, json=product_data)
        if r:
            print(f"✅ Updated product info: {handle}")
        else:
            print(f"❌ Failed to update product info: {handle}")
    else:
        r = request_with_retry("POST", f"{SHOP_URL}/products.json", headers=shopify_headers, json=product_data)
        if r:
            product_id = r.json()["product"]["id"]
            print(f"✅ Created product: {handle}")
        else:
            print(f"❌ Failed to create product: {handle}")
            return

    # -------------------------------
    # 3️⃣ Update variants (price)
    # -------------------------------
    for variant in variants_data:
        variant_update = {"variant": {"id": variant["id"], "price": variant["price"]}}
        r = request_with_retry("PUT", f"{SHOP_URL}/variants/{variant['id']}.json", headers=shopify_headers, json=variant_update)
        if r:
            print(f"✅ Updated price for variant {variant['option1']}")
        else:
            print(f"❌ Failed to update price for variant {variant['option1']}")

    # -------------------------------
    # 4️⃣ Update inventory levels
    # -------------------------------
    for variant in variants_data:
        inventory_item_id = get_inventory_item_id(variant["id"])
        if inventory_item_id:
            inventory_payload = {
                "location_id": int(LOCATION_ID),
                "inventory_item_id": inventory_item_id,
                "available": variant["inventory_quantity"]
            }
            r = request_with_retry("POST", f"{SHOP_URL}/inventory_levels/set.json", headers=shopify_headers, json=inventory_payload)
            if r:
                print(f"✅ Updated inventory for variant {variant['option1']}")
            else:
                print(f"❌ Failed to update inventory for variant {variant['option1']}")

# -------------------------------
# HELPER: get inventory_item_id for a variant
# -------------------------------
def get_inventory_item_id(variant_id):
    r = request_with_retry("GET", f"{SHOP_URL}/variants/{variant_id}.json", headers=shopify_headers)
    if r:
        return r.json()["variant"]["inventory_item_id"]
    return None

# -------------------------------
# RUN
# -------------------------------
if __name__ == "__main__":
    sync_product_2000133()
