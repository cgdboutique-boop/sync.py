import os
import requests
import time
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Shopify store info
SHOPIFY_STORE = os.getenv("SHOPIFY_STORE")
SHOPIFY_TOKEN = os.getenv("SHOPIFY_TOKEN")
SHOPIFY_API_VERSION = "2023-10"

if not SHOPIFY_STORE or not SHOPIFY_TOKEN:
    raise Exception("SHOPIFY_STORE or SHOPIFY_TOKEN missing")

shopify_headers = {
    "Content-Type": "application/json",
    "X-Shopify-Access-Token": SHOPIFY_TOKEN
}

# Supplier API info
SUPPLIER_API_URL = os.getenv("SUPPLIER_API_URL")
SUPPLIER_TOKEN = os.getenv("SUPPLIER_TOKEN")

if not SUPPLIER_API_URL or not SUPPLIER_TOKEN:
    raise Exception("SUPPLIER_API_URL or SUPPLIER_TOKEN missing")

supplier_headers = {"Authorization": f"Bearer {SUPPLIER_TOKEN}"}


# ---- Safe request with retries ----
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


# ---- Fetch supplier products ----
def fetch_supplier_products():
    r = safe_request("GET", SUPPLIER_API_URL, headers=supplier_headers)
    try:
        return r.json().get("products", [])
    except Exception:
        print("⚠️ Supplier response not JSON:", r.text)
        return []


# ---- Fetch Shopify variants mapped by SKU ----
def fetch_shopify_variants():
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
        time.sleep(0.5)  # short delay to respect Shopify limits

    print(f"✅ Fetched {len(variants_by_sku)} Shopify variants")
    return variants_by_sku


# ---- Get Shopify location ID ----
def get_location_id():
    url = f"https://{SHOPIFY_STORE}.myshopify.com/admin/api/{SHOPIFY_API_VERSION}/locations.json"
    r = safe_request("GET", url, headers=shopify_headers)
    return r.json()["locations"][0]["id"]


# ---- Update price ----
def update_price(variant_id, new_price, sku):
    url = f"https://{SHOPIFY_STORE}.myshopify.com/admin/api/{SHOPIFY_API_VERSION}/variants/{variant_id}.json"
    payload = {"variant": {"id": variant_id, "price": new_price}}
    safe_request("PUT", url, headers=shopify_headers, json=payload)
    print(f"✅ Updated price for SKU {sku} → {new_price}")


# ---- Update inventory ----
def update_inventory(inventory_item_id, location_id, quantity, sku):
    url = f"https://{SHOPIFY_STORE}.myshopify.com/admin/api/{SHOPIFY_API_VERSION}/inventory_levels/set.json"
    payload = {
        "location_id": location_id,
        "inventory_item_id": inventory_item_id,
        "available": int(quantity)
    }
    safe_request("POST", url, headers=shopify_headers, json=payload)
    print(f"✅ Inventory for SKU {sku} set to {quantity}")


# ---- Main sync ----
def main():
    print("🔹 Starting Shopify Sync...")
    shopify_variants = fetch_shopify_variants()
    supplier_products = fetch_supplier_products()
    location_id = get_location_id()
    print(f"🔹 Fetched {len(supplier_products)} supplier products")

    for product in supplier_products:
        sku = str(product.get("sku"))
        price = product.get("price")
        quantity = product.get("quantity", 0)

        if sku not in shopify_variants:
            continue

        variant = shopify_variants[sku]
        variant_id = variant["id"]
        inventory_item_id = variant["inventory_item_id"]

        # price update
        if str(variant.get("price")) != str(price):
            update_price(variant_id, price, sku)
            time.sleep(0.3)  # delay per Shopify API recommendations

        # inventory update
        update_inventory(inventory_item_id, location_id, quantity, sku)
        time.sleep(0.3)  # delay


if __name__ == "__main__":
    main()

