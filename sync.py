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

if not SHOPIFY_STORE or not SHOPIFY_TOKEN or not SUPPLIER_API_URL or not SUPPLIER_TOKEN:
    raise ValueError("One or more required environment variables are not set!")

SHOP_URL = f"https://{SHOPIFY_STORE}.myshopify.com/admin/api/2025-07"
shopify_headers = {
    "X-Shopify-Access-Token": SHOPIFY_TOKEN,
    "Content-Type": "application/json",
    "Accept": "application/json"
}

# Supplier headers – adjust to your supplier’s docs
supplier_headers = {
    "X-Auth-Token": SUPPLIER_TOKEN,
    "Accept": "application/json"
}

# -------------------------------
# HELPER FUNCTIONS
# -------------------------------
def request_with_retry(method, url, headers=None, json=None, max_retries=5):
    retry_delay = 2
    for attempt in range(max_retries):
        try:
            response = requests.request(method, url, headers=headers, json=json)
            if response.status_code in [429, 401, 422]:
                wait = int(response.headers.get("Retry-After", retry_delay))
                print(f"{response.status_code} from {url}. Retrying in {wait}s...")
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

def get_shopify_location_id():
    r = request_with_retry("GET", f"{SHOP_URL}/locations.json", headers=shopify_headers)
    if not r:
        raise RuntimeError("❌ Could not fetch Shopify locations")
    locations = r.json().get("locations", [])
    if not locations:
        raise RuntimeError("❌ No Shopify locations found")
    location_id = locations[0]["id"]
    print(f"📦 Using Shopify location_id: {location_id}")
    return location_id

# -------------------------------
# SUPPLIER FUNCTIONS
# -------------------------------
def fetch_supplier_product(product_id):
    """Fetch product details from supplier API"""
    url = f"{SUPPLIER_API_URL}/products/{product_id}"
    r = request_with_retry("GET", url, headers=supplier_headers)
    if not r:
        raise RuntimeError(f"❌ Failed to fetch supplier product {product_id}")
    return r.json()

# -------------------------------
# SYNC ONE PRODUCT
# -------------------------------
def sync_product_from_supplier(product_id):
    supplier_data = fetch_supplier_product(product_id)

    # Map supplier → Shopify fields (adjust based on real supplier JSON)
    title = supplier_data.get("title", f"Product {product_id}")
    body_html = supplier_data.get("description", "")
    vendor = supplier_data.get("brand", "Supplier")
    product_type = supplier_data.get("category", "General")
    tags = ",".join(supplier_data.get("tags", []))

    # Variants
    supplier_variants = []
    for v in supplier_data.get("variants", []):
        supplier_variants.append({
            "option1": v.get("size") or v.get("option"),
            "sku": v.get("sku"),
            "price": v.get("price"),
            "stock": v.get("stock", 0)
        })

    # Images
    supplier_images = [{"src": img["url"]} for img in supplier_data.get("images", [])]

    # Build Shopify product payload
    product_data = {
        "product": {
            "title": title,
            "body_html": body_html,
            "vendor": vendor,
            "product_type": product_type,
            "tags": tags,
            "handle": str(product_id),
            "variants": [
                {
                    "option1": v["option1"],
                    "sku": v["sku"],
                    "price": v["price"],
                    "inventory_management": "shopify"
                } for v in supplier_variants
            ],
            "images": supplier_images
        }
    }

    # Check if product exists
    r = request_with_retry("GET", f"{SHOP_URL}/products.json?handle={product_id}", headers=shopify_headers)
    existing_products = r.json().get("products", []) if r else []
    if existing_products:
        product_id_shopify = existing_products[0]["id"]
        r = request_with_retry("PUT", f"{SHOP_URL}/products/{product_id_shopify}.json",
                               headers=shopify_headers, json=product_data)
        if not r:
            print(f"❌ Failed to update Shopify product {product_id}")
            return
        print(f"✅ Updated Shopify product {product_id}")
        shop_product = r.json()["product"]
    else:
        r = request_with_retry("POST", f"{SHOP_URL}/products.json",
                               headers=shopify_headers, json=product_data)
        if not r:
            print(f"❌ Failed to create Shopify product {product_id}")
            return
        print(f"✅ Created Shopify product {product_id}")
        shop_product = r.json()["product"]

    # -------------------------------
    # Update inventory levels
    # -------------------------------
    location_id = get_shopify_location_id()
    shop_variants = { v["sku"]: v for v in shop_product["variants"] }

    for sv in supplier_variants:
        sku = sv["sku"]
        stock = sv["stock"]
        shop_v = shop_variants.get(sku)
        if not shop_v:
            print(f"⚠️ Shopify variant missing for {sku}")
            continue
        inventory_item_id = shop_v["inventory_item_id"]
        payload = {
            "location_id": location_id,
            "inventory_item_id": inventory_item_id,
            "available": stock
        }
        r = request_with_retry("POST", f"{SHOP_URL}/inventory_levels/set.json",
                               headers=shopify_headers, json=payload)
        if r:
            print(f"   ✅ Stock updated for {sku} → {stock}")
        else:
            print(f"   ❌ Failed to update stock for {sku}")

# -------------------------------
# RUN
# -------------------------------
if __name__ == "__main__":
    # Example: sync product 2000133
    sync_product_from_supplier("2000133")
