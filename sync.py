import os
import requests
import time

# -------------------------------
# CONFIG (from GitHub secrets)
# -------------------------------
SHOPIFY_STORE = os.environ.get("SHOPIFY_STORE")
SHOPIFY_TOKEN = os.environ.get("SHOPIFY_TOKEN")
SHOPIFY_LOCATION_ID = os.environ.get("SHOPIFY_LOCATION_ID")  # For inventory updates

if not SHOPIFY_STORE or not SHOPIFY_TOKEN or not SHOPIFY_LOCATION_ID:
    raise ValueError("SHOPIFY_STORE, SHOPIFY_TOKEN, or SHOPIFY_LOCATION_ID is not set!")

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

    # Variants from supplier
    variants = [
        {"option1": "6-12M", "sku": "2000133", "price": 220},
        {"option1": "12-18M", "sku": "2000133", "price": 220},
        {"option1": "18-24M", "sku": "2000133", "price": 220}
    ]

    # Images linked to variants
    images = [
        {"src": "https://cdn.shopify.com/s/files/1/0551/4638/1501/files/6-12M_image.png", "position": 1, "variant_ids": []},
        {"src": "https://cdn.shopify.com/s/files/1/0551/4638/1501/files/12-18M_image.png", "position": 2, "variant_ids": []},
        {"src": "https://cdn.shopify.com/s/files/1/0551/4638/1501/files/18-24M_image.png", "position": 3, "variant_ids": []},
    ]

    # Check if product exists
    r = request_with_retry("GET", f"{SHOP_URL}/products.json?handle={handle}", headers=shopify_headers)
    existing_products = r.json().get("products", []) if r else []

    product_data = {
        "product": {
            "title": title,
            "body_html": body_html,
            "vendor": vendor,
            "product_type": product_type,
            "tags": tags,
            "handle": handle,
            "variants": variants,
            "images": images
        }
    }

    if existing_products:
        product_id = existing_products[0]["id"]
        print(f"Updating product {handle} (ID: {product_id})...")
        r = request_with_retry("PUT", f"{SHOP_URL}/products/{product_id}.json", headers=shopify_headers, json=product_data)
        if r:
            print(f"✅ Updated product: {handle}")
        else:
            print(f"❌ Failed to update product: {handle}")
    else:
        print(f"Creating new product {handle}...")
        r = request_with_retry("POST", f"{SHOP_URL}/products.json", headers=shopify_headers, json=product_data)
        if r:
            print(f"✅ Created product: {handle}")
        else:
            print(f"❌ Failed to create product: {handle}")
        product_id = r.json()["product"]["id"] if r else None

    # Update inventory for each variant
    if product_id:
        r = request_with_retry("GET", f"{SHOP_URL}/products/{product_id}/variants.json", headers=shopify_headers)
        if r:
            for variant in r.json().get("variants", []):
                qty = 5
                if variant["option1"] == "12-18M":
                    qty = 90
                elif variant["option1"] == "18-24M":
                    qty = 100
                inv_data = {
                    "location_id": int(SHOPIFY_LOCATION_ID),
                    "inventory_item_id": int(variant["inventory_item_id"]),
                    "available": qty
                }
                r_inv = request_with_retry("POST", f"{SHOP_URL}/inventory_levels/set.json", headers=shopify_headers, json=inv_data)
                if r_inv:
                    print(f"✅ Updated inventory for variant {variant['option1']} to {qty}")
                else:
                    print(f"❌ Failed inventory update for variant {variant['option1']}")

# -------------------------------
# RUN
# -------------------------------
if __name__ == "__main__":
    sync_product_2000133()
