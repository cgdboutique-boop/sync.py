import os
import sys
import requests
import time

# -------------------------------
# CONFIGURATION
# -------------------------------
SHOPIFY_STORE = os.environ.get("SHOPIFY_STORE")
SHOPIFY_TOKEN = os.environ.get("SHOPIFY_TOKEN")
SUPPLIER_API_URL = os.environ.get("SUPPLIER_API_URL")
SUPPLIER_API_TOKEN = os.environ.get("SUPPLIER_TOKEN")  # matches your workflow

if not all([SHOPIFY_STORE, SHOPIFY_TOKEN, SUPPLIER_API_URL, SUPPLIER_API_TOKEN]):
    raise ValueError("Missing environment variables!")

SHOP_URL = f"https://{SHOPIFY_STORE}.myshopify.com/admin/api/2025-07"
shopify_headers = {
    "X-Shopify-Access-Token": SHOPIFY_TOKEN,
    "Content-Type": "application/json"
}
supplier_headers = {
    "Authorization": f"Bearer {SUPPLIER_API_TOKEN}",
    "Content-Type": "application/json"
}

# -------------------------------
# HELPER: Request with Retry
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
# FETCH: Supplier Products
# -------------------------------
def fetch_all_supplier_products():
    url = f"{SUPPLIER_API_URL}/products"
    r = request_with_retry("GET", url, headers=supplier_headers)
    return r.json().get("products", []) if r else []

# -------------------------------
# MAP: Supplier → Shopify Format
# -------------------------------
def map_supplier_to_shopify(supplier_product):
    return {
        "product": {
            "title": supplier_product["title"],
            "body_html": supplier_product.get("description", ""),
            "vendor": supplier_product.get("vendor", "Unknown"),
            "product_type": supplier_product.get("type", ""),
            "tags": ", ".join(supplier_product.get("tags", [])),
            "handle": supplier_product["handle"],
            "variants": [
                {
                    "option1": v["size"],
                    "sku": v["sku"],
                    "inventory_management": "shopify",
                    "inventory_quantity": v["stock"],
                    "price": v["price"]
                } for v in supplier_product.get("variants", [])
            ],
            "images": [
                {
                    "src": img["url"],
                    "position": idx + 1
                } for idx, img in enumerate(supplier_product.get("images", []))
            ]
        }
    }

# -------------------------------
# INVENTORY: Location & Update
# -------------------------------
def get_location_id():
    r = request_with_retry("GET", f"{SHOP_URL}/locations.json", headers=shopify_headers)
    locations = r.json().get("locations", []) if r else []
    return locations[0]["id"] if locations else None

def update_inventory(inventory_item_id, location_id, quantity):
    payload = {
        "location_id": location_id,
        "inventory_item_id": inventory_item_id,
        "available": quantity
    }
    r = request_with_retry("POST", f"{SHOP_URL}/inventory_levels/set.json", headers=shopify_headers, json=payload)
    return r

# -------------------------------
# SYNC: All Products
# -------------------------------
def sync_all_products(limit=None):
    location_id = get_location_id()
    if not location_id:
        print("❌ Could not retrieve location ID.")
        return

    supplier_products = fetch_all_supplier_products()
    if limit:
        supplier_products = supplier_products[:limit]

    for sp in supplier_products:
        handle = sp["handle"]
        product_data = map_supplier_to_shopify(sp)

        r = request_with_retry("GET", f"{SHOP_URL}/products.json?handle={handle}", headers=shopify_headers)
        existing_products = r.json().get("products", []) if r else []

        if existing_products:
            product_id = existing_products[0]["id"]
            r = request_with_retry("PUT", f"{SHOP_URL}/products/{product_id}.json", headers=shopify_headers, json=product_data)
            print(f"✅ Updated product: {handle}" if r else f"❌ Failed to update product: {handle}")
        else:
            r = request_with_retry("POST", f"{SHOP_URL}/products.json", headers=shopify_headers, json=product_data)
            print(f"✅ Created product: {handle}" if r else f"❌ Failed to create product: {handle}")

        # Update inventory for each variant
        if r:
            product = r.json().get("product", {})
            for variant in product.get("variants", []):
                inventory_item_id = variant.get("inventory_item_id")
                matching_variant = next((v for v in product_data["product"]["variants"] if v["sku"] == variant["sku"]), None)
                quantity = matching_variant.get("inventory_quantity") if matching_variant else None
                if inventory_item_id and quantity is not None:
                    update_inventory(inventory_item_id, location_id, quantity)

# -------------------------------
# MAIN ENTRY POINT
# -------------------------------
if __name__ == "__main__":
    limit = None
    if "--limit" in sys.argv:
        try:
            limit_index = sys.argv.index("--limit") + 1
            limit = int(sys.argv[limit_index])
        except (IndexError, ValueError):
            print("⚠️ Invalid limit value. Ignoring.")
    sync_all_products(limit=limit)
