import os
import requests
import time

# Load environment variables from GitHub Actions
SUPPLIER_API_URL = os.getenv("SUPPLIER_API_URL")
SUPPLIER_TOKEN = os.getenv("SUPPLIER_TOKEN")
SHOPIFY_TOKEN = os.getenv("SHOPIFY_TOKEN")
SHOPIFY_STORE = "cgdboutique"
SHOPIFY_API_VERSION = "2023-10"

# API headers
supplier_headers = {"Authorization": f"Bearer {SUPPLIER_TOKEN}"}
shopify_headers = {"X-Shopify-Access-Token": SHOPIFY_TOKEN}
SHOPIFY_URL = f"https://{SHOPIFY_STORE}.myshopify.com/admin/api/{SHOPIFY_API_VERSION}"

# Safe request with retries
def safe_request(method, url, **kwargs):
    retries = 5
    for attempt in range(retries):
        try:
            r = requests.request(method, url, timeout=30, **kwargs)
            r.raise_for_status()
            return r
        except requests.exceptions.RequestException as e:
            wait = 2 ** attempt
            print(f"⚠️ Request failed ({e}). Attempt {attempt+1}/{retries}, retrying in {wait}s...")
            time.sleep(wait)
    raise Exception(f"Failed after {retries} retries: {url}")

# Fetch supplier products
def fetch_supplier_products():
    r = safe_request("GET", SUPPLIER_API_URL, headers=supplier_headers)
    return r.json()

# Fetch Shopify variants by SKU
def fetch_shopify_variants():
    variants_by_sku = {}
    next_page = f"{SHOPIFY_URL}/variants.json?limit=250"

    while next_page:
        r = safe_request("GET", next_page, headers=shopify_headers)
        data = r.json()
        for v in data.get("variants", []):
            if v.get("sku"):
                variants_by_sku[str(v["sku"])] = v

        # Handle pagination
        next_page = r.links.get("next", {}).get("url")

    print(f"✅ Fetched {len(variants_by_sku)} Shopify variants by SKU")
    return variants_by_sku

# Get first location ID
def get_location_id():
    url = f"{SHOPIFY_URL}/locations.json"
    r = safe_request("GET", url, headers=shopify_headers)
    return r.json()["locations"][0]["id"]

# Update price
def update_price(variant_id, new_price, sku):
    url = f"{SHOPIFY_URL}/variants/{variant_id}.json"
    payload = {"variant": {"id": variant_id, "price": str(new_price)}}
    r = safe_request("PUT", url, headers=shopify_headers, json=payload)
    print(f"💰 Updated price for SKU {sku} → {new_price}")

# Update inventory
def update_inventory(inventory_item_id, location_id, target_quantity, sku):
    url = f"{SHOPIFY_URL}/inventory_levels/set.json"
    payload = {
        "location_id": location_id,
        "inventory_item_id": inventory_item_id,
        "available": int(target_quantity),
    }
    r = safe_request("POST", url, headers=shopify_headers, json=payload)
    print(f"📦 Inventory for SKU {sku} set to {target_quantity}")

# Main sync
def main():
    shopify_variants = fetch_shopify_variants()
    supplier_products = fetch_supplier_products()
    location_id = get_location_id()
    print(f"✅ Fetched {len(supplier_products)} supplier products")

    seen_inventory_items = set()

    for product in supplier_products:
        sku = str(product.get("sku"))
        price = product.get("price")
        quantity = product.get("quantity", 0)

        if not sku or sku not in shopify_variants:
            continue

        variant = shopify_variants[sku]
        variant_id = variant["id"]
        inventory_item_id = variant["inventory_item_id"]

        # Update price if different
        if str(variant.get("price")) != str(price):
            update_price(variant_id, price, sku)

        # Update inventory once per item
        if inventory_item_id not in seen_inventory_items:
            update_inventory(inventory_item_id, location_id, quantity, sku)
            seen_inventory_items.add(inventory_item_id)

if __name__ == "__main__":
    main()
