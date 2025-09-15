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
    print(f"=== Syncing product: {handle} ===")
    sp = fetch_supplier_product(handle)
    if not sp:
        print(f"No product found in supplier: {handle}")
        return

    # Extract product info
    title = sp.get("title", "")
    body_html = sp.get("body_html", "")
    vendor = sp.get("vendor", "")
    product_type = sp.get("product_type", "")
    tags = sp.get("tags", "")
    variants_data = sp.get("variants", [])
    images_data = sp.get("images", [])

    if not variants_data:
        print(f"Skipping product missing variants: {handle}")
        return

    # Prepare variants
    variants = []
    images = []
    for idx, v in enumerate(variants_data, start=1):
        variant_name = v.get("option1", "")
        sku = v.get("sku", "")
        inventory = v.get("inventory_quantity", 0)
        price = v.get("price", 0)
        image_src = v.get("image_src", "")
        if not variant_name or not sku:
            print(f"Skipping variant missing essential data: {v}")
            continue

        variants.append({
            "option1": variant_name,
            "sku": sku,
            "inventory_quantity": inventory,
            "price": price,
            "image_src": image_src
        })

        # Add image with position
        if image_src:
            images.append({
                "src": image_src,
                "position": idx
            })

    if not variants:
        print(f"No valid variants to sync for product: {handle}")
        return

    # Check if product exists in Shopify
    r = request_with_retry("GET", f"{SHOP_URL}/products.json?handle={handle}", headers=shopify_headers)
    existing_products = r.json().get("products", []) if r else []
    existing = existing_products[0] if existing_products else None

    # Prepare product payload
    product_data = {
        "product": {
            "title": title,
            "body_html": body_html,
            "vendor": vendor,
            "product_type": product_type,
            "tags": tags,
            "handle": handle,
            "images": images,
            "variants": variants
        }
    }

    # Create or update product
    if existing:
        product_id = existing["id"]
        r = request_with_retry("PUT", f"{SHOP_URL}/products/{product_id}.json", headers=shopify_headers, json=product_data)
        if r:
            print(f"Updated product: {handle}")
        else:
            print(f"Failed to update product: {handle}")
    else:
        r = request_with_retry("POST", f"{SHOP_URL}/products.json", headers=shopify_headers, json=product_data)
        if r:
            print(f"Created product: {handle}")
        else:
            print(f"Failed to create product: {handle}")

    print("✅ Sync completed.\n")

# -------------------------------
# RUN
# -------------------------------
if __name__ == "__main__":
    # Example: sync one product handle
    sync_single_product("2000133")  # replace with your product handle
