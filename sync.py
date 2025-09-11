import os
import requests
import time
from dotenv import load_dotenv

load_dotenv()

# Shopify API setup
SHOPIFY_STORE = os.getenv("SHOPIFY_STORE")
SHOPIFY_API_VERSION = "2023-10"
SHOPIFY_API_KEY = os.getenv("SHOPIFY_API_KEY")
SHOPIFY_PASSWORD = os.getenv("SHOPIFY_PASSWORD")
SHOPIFY_URL = f"https://{SHOPIFY_API_KEY}:{SHOPIFY_PASSWORD}@{SHOPIFY_STORE}.myshopify.com/admin/api/{SHOPIFY_API_VERSION}"

# Supplier API setup
SUPPLIER_API_URL = os.getenv("SUPPLIER_API_URL")
SUPPLIER_TOKEN = os.getenv("SUPPLIER_TOKEN")
supplier_headers = {"Authorization": f"Bearer {SUPPLIER_TOKEN}"}

# Safe request with retries
def safe_request(method, url, headers=None, json=None, retries=5):
    delay = 1
    for attempt in range(1, retries + 1):
        try:
            if method.upper() == "GET":
                r = requests.get(url, headers=headers)
            elif method.upper() == "POST":
                r = requests.post(url, headers=headers, json=json)
            elif method.upper() == "PUT":
                r = requests.put(url, headers=headers, json=json)
            else:
                raise ValueError("Unsupported HTTP method")
            r.raise_for_status()
            return r
        except requests.exceptions.RequestException as e:
            print(f"⚠️ Request failed ({e}). Attempt {attempt}/{retries}, retrying in {delay}s...")
            time.sleep(delay)
            delay *= 2
    raise Exception(f"Failed after {retries} retries: {url}")

# Fetch supplier products
def fetch_supplier_products():
    r = safe_request("GET", SUPPLIER_API_URL, headers=supplier_headers)
    return r.json()

# Fetch Shopify variants mapped by SKU
def fetch_shopify_variants():
    variants_by_sku = {}
    page = 1
    while True:
        url = f"{SHOPIFY_URL}/variants.json?limit=250&page={page}"
        r = safe_request("GET", url)
        variants = r.json().get("variants", [])
        if not variants:
            break
        for v in variants:
            if v.get("sku"):
                variants_by_sku[v["sku"]] = v
        page += 1
    print(f"✅ Fetched {len(variants_by_sku)} Shopify variants by SKU")
    return variants_by_sku

# Fetch first location ID
def get_location_id():
    url = f"{SHOPIFY_URL}/locations.json"
    r = safe_request("GET", url)
    locations = r.json().get("locations", [])
    if not locations:
        raise Exception("No Shopify location found")
    return locations[0]["id"]

# Update variant price
def update_price(variant_id, new_price, sku):
    url = f"{SHOPIFY_URL}/variants/{variant_id}.json"
    payload = {"variant": {"id": variant_id, "price": new_price}}
    r = safe_request("PUT", url, json=payload)
    print(f"Updated price for variant {variant_id} (SKU {sku}) to {new_price:.2f}")

# Update inventory safely
def update_inventory(inventory_item_id, location_id, quantity, sku):
    url = f"{SHOPIFY_URL}/inventory_levels/set.json"
    payload = {
        "location_id": location_id,
        "inventory_item_id": inventory_item_id,
        "available": int(quantity)
    }
    try:
        r = safe_request("POST", url, json=payload)
        print(f"Inventory for item {inventory_item_id} (SKU {sku}) set to {quantity}")
    except Exception as e:
        print(f"⚠️ Failed to set inventory for item {inventory_item_id} (SKU {sku}): {e}")

# Main sync
def main():
    shopify_variants = fetch_shopify_variants()
    supplier_products = fetch_supplier_products()
    location_id = get_location_id()
    print(f"Fetched {len(supplier_products)} supplier products")

    seen_inventory_items = set()

    for product in supplier_products:
        sku = str(product.get("sku"))
        price = product.get("price")
        quantity = product.get("quantity", 0)

        if sku not in shopify_variants:
            print(f"Skipping SKU {sku}: not found in Shopify")
            continue

        variant = shopify_variants[sku]
        variant_id = variant["id"]
        inventory_item_id = variant["inventory_item_id"]

        # Update price if different
        if str(variant.get("price")) != str(price):
            update_price(variant_id, price, sku)

        # Update inventory if not already done
        if inventory_item_id not in seen_inventory_items:
            update_inventory(inventory_item_id, location_id, quantity, sku)
            seen_inventory_items.add(inventory_item_id)
        else:
            print(f"Skipping duplicate inventory update for item {inventory_item_id}")

if __name__ == "__main__":
    main()
