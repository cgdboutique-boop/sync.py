import os
import requests
import time

# -------------------------
# Load environment variables
# -------------------------
SHOPIFY_STORE = "cgdboutique"
SHOPIFY_API_VERSION = "2023-10"
SHOPIFY_TOKEN = os.getenv("SHOPIFY_TOKEN")
SUPPLIER_API_URL = os.getenv("SUPPLIER_API_URL")
SUPPLIER_TOKEN = os.getenv("SUPPLIER_TOKEN")

if not SHOPIFY_TOKEN:
    raise Exception("SHOPIFY_TOKEN is missing")
if not SUPPLIER_API_URL:
    raise Exception("SUPPLIER_API_URL is missing")
if not SUPPLIER_TOKEN:
    raise Exception("SUPPLIER_TOKEN is missing")

# -------------------------
# Headers
# -------------------------
shopify_headers = {
    "Content-Type": "application/json",
    "X-Shopify-Access-Token": SHOPIFY_TOKEN,
}

supplier_headers = {
    "X-Shopify-Access-Token": SUPPLIER_TOKEN
}

# -------------------------
# Safe request with retries
# -------------------------
def safe_request(method, url, **kwargs):
    for attempt in range(5):
        try:
            r = requests.request(method, url, timeout=30, **kwargs)
            r.raise_for_status()
            return r
        except requests.exceptions.RequestException as e:
            print(f"⚠️ Request failed ({e}). Attempt {attempt+1}/5")
            time.sleep(2 ** attempt)
    raise Exception(f"Failed after 5 retries: {url}")

# -------------------------
# Fetch supplier products
# -------------------------
def fetch_supplier_products():
    print("🔹 Fetching supplier products...")
    r = safe_request("GET", SUPPLIER_API_URL, headers=supplier_headers)

    # Debug supplier response
    if not r.text:
        raise Exception("Supplier response is empty")
    try:
        data = r.json()
    except Exception as e:
        print("⚠️ Supplier response not JSON:", r.text)
        raise e
    products = data.get("products", [])
    print(f"✅ Fetched {len(products)} supplier products")
    return products

# -------------------------
# Fetch Shopify variants mapped by SKU
# -------------------------
def fetch_shopify_variants():
    print("🔹 Fetching Shopify variants by SKU...")
    variants_by_sku = {}
    url = f"https://{SHOPIFY_STORE}.myshopify.com/admin/api/{SHOPIFY_API_VERSION}/variants.json?limit=250"

    while url:
        r = safe_request("GET", url, headers=shopify_headers)
        data = r.json()
        for v in data.get("variants", []):
            if v.get("sku"):
                variants_by_sku[v["sku"]] = v

        # pagination
        url = r.links.get("next", {}).get("url")

        # Delay to avoid Shopify API rate limits
        time.sleep(0.5)

    print(f"✅ Fetched {len(variants_by_sku)} Shopify variants")
    return variants_by_sku

# -------------------------
# Get location ID
# -------------------------
def get_location_id():
    url = f"https://{SHOPIFY_STORE}.myshopify.com/admin/api/{SHOPIFY_API_VERSION}/locations.json"
    r = safe_request("GET", url, headers=shopify_headers)
    location_id = r.json()["locations"][0]["id"]
    print(f"🔹 Using location ID: {location_id}")
    return location_id

# -------------------------
# Update price
# -------------------------
def update_price(variant_id, new_price, sku):
    url = f"https://{SHOPIFY_STORE}.myshopify.com/admin/api/{SHOPIFY_API_VERSION}/variants/{variant_id}.json"
    payload = {"variant": {"id": variant_id, "price": new_price}}
    safe_request("PUT", url, headers=shopify_headers, json=payload)
    print(f"✅ Updated price for variant {variant_id} (SKU {sku}) → {new_price:.2f}")
    time.sleep(0.3)  # Delay to avoid hitting Shopify limits

# -------------------------
# Update inventory
# -------------------------
def update_inventory(inventory_item_id, location_id, quantity, sku):
    url = f"https://{SHOPIFY_STORE}.myshopify.com/admin/api/{SHOPIFY_API_VERSION}/inventory_levels/set.json"
    payload = {
        "location_id": location_id,
        "inventory_item_id": inventory_item_id,
        "available": int(quantity)
    }
    safe_request("POST", url, headers=shopify_headers, json=payload)
    print(f"✅ Inventory for item {inventory_item_id} (SKU {sku}) set to {quantity}")
    time.sleep(0.3)  # Delay to avoid hitting Shopify limits

# -------------------------
# Main sync
# -------------------------
def main():
    print("🔹 Starting Shopify Sync...")
    shopify_variants = fetch_shopify_variants()
    supplier_products = fetch_supplier_products()
    location_id = get_location_id()

    seen_inventory_items = set()

    for product in supplier_products:
        for variant in product.get("variants", []):
            sku = variant.get("sku")
            price = variant.get("price")
            quantity = variant.get("inventory_quantity", 0)

            if sku not in shopify_variants:
                continue

            shopify_variant = shopify_variants[sku]
            variant_id = shopify_variant["id"]
            inventory_item_id = shopify_variant["inventory_item_id"]

            # Price update
            if str(shopify_variant.get("price")) != str(price):
                update_price(variant_id, price, sku)

            # Inventory update
            if inventory_item_id not in seen_inventory_items:
                update_inventory(inventory_item_id, location_id, quantity, sku)
                seen_inventory_items.add(inventory_item_id)

    print("✅ Shopify sync completed!")

if __name__ == "__main__":
    main()
