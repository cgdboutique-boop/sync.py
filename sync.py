import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()

# Shopify API setup
SHOPIFY_STORE = "cgdboutique"
SHOPIFY_API_VERSION = "2023-10"
SHOPIFY_API_KEY = os.getenv("SHOPIFY_API_KEY")
SHOPIFY_PASSWORD = os.getenv("SHOPIFY_PASSWORD")
SHOPIFY_URL = f"https://{SHOPIFY_API_KEY}:{SHOPIFY_PASSWORD}@{SHOPIFY_STORE}.myshopify.com/admin/api/{SHOPIFY_API_VERSION}"

# Supplier API setup
SUPPLIER_API_URL = os.getenv("SUPPLIER_API_URL")
SUPPLIER_TOKEN = os.getenv("SUPPLIER_TOKEN")
supplier_headers = {"Authorization": f"Bearer {SUPPLIER_TOKEN}"}

# --- Utility: retry wrapper for Shopify API calls ---
def safe_request(method, url, **kwargs):
    for attempt in range(5):  # up to 5 retries
        r = requests.request(method, url, **kwargs)
        if r.status_code == 429:  # Rate limit hit
            wait_time = int(r.headers.get("Retry-After", 2))
            print(f"⏳ Rate limited. Retrying in {wait_time}s...")
            time.sleep(wait_time)
            continue
        if r.status_code >= 500:  # Server error
            print(f"⚠️ Shopify server error {r.status_code}. Retrying...")
            time.sleep(2)
            continue
        r.raise_for_status()
        return r
    r.raise_for_status()
    return r

# --- Fetch supplier products ---
def fetch_supplier_products():
    r = requests.get(SUPPLIER_API_URL, headers=supplier_headers)
    r.raise_for_status()
    return r.json()

# --- Fetch Shopify variants mapped by SKU ---
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
    print(f"✅ Fetched {len(variants_by_sku)} existing Shopify variants by SKU")
    return variants_by_sku

# --- Fetch location ID ---
def get_location_id():
    url = f"{SHOPIFY_URL}/locations.json"
    r = safe_request("GET", url)
    return r.json()["locations"][0]["id"]

# --- Update price ---
def update_price(variant_id, new_price, sku):
    url = f"{SHOPIFY_URL}/variants/{variant_id}.json"
    r = safe_request("PUT", url, json={"variant": {"id": variant_id, "price": new_price}})
    print(f"💰 Updated price for variant {variant_id} (SKU #{sku}) to {new_price:.2f}")

# --- Update inventory using set.json only ---
def update_inventory(inventory_item_id, location_id, target_quantity, sku):
    url = f"{SHOPIFY_URL}/inventory_levels/set.json"
    payload = {
        "location_id": location_id,
        "inventory_item_id": inventory_item_id,
        "available": int(target_quantity)
    }
    r = safe_request("POST", url, json=payload)
    if r.status_code == 200:
        print(f"📦 Inventory for item {inventory_item_id} (SKU #{sku}) set to {target_quantity}")
    else:
        print(f"⚠️ Failed to set inventory for item {inventory_item_id} (SKU #{sku}): {r.text}")

# --- Main sync ---
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

        if not sku:
            print("⚠️ Supplier product missing SKU, skipping...")
            continue

        if sku not in shopify_variants:
            print(f"❌ SKU not found in Shopify: {sku}")
            continue

        variant = shopify_variants[sku]
        variant_id = variant["id"]
        inventory_item_id = variant["inventory_item_id"]

        # --- Update price if changed ---
        if str(variant.get("price")) != str(price):
            update_price(variant_id, price, sku)

        # --- Update inventory if not already updated ---
        if inventory_item_id not in seen_inventory_items:
            update_inventory(inventory_item_id, location_id, quantity, sku)
            seen_inventory_items.add(inventory_item_id)
        else:
            print(f"⏭️ Skipping duplicate inventory update for item {inventory_item_id}")

if __name__ == "__main__":
    main()
