import os
import requests
import time
import sys

print("🔹 Starting Shopify Sync...")

# ---- GitHub secrets ----
SHOPIFY_STORE = os.getenv("SHOPIFY_STORE")
SHOPIFY_TOKEN = os.getenv("SHOPIFY_TOKEN")
SUPPLIER_API_URL = os.getenv("SUPPLIER_API_URL")
SUPPLIER_TOKEN = os.getenv("SUPPLIER_TOKEN")

if not all([SHOPIFY_STORE, SHOPIFY_TOKEN, SUPPLIER_API_URL, SUPPLIER_TOKEN]):
    raise Exception("❌ One or more GitHub secrets missing: SHOPIFY_STORE, SHOPIFY_TOKEN, SUPPLIER_API_URL, SUPPLIER_TOKEN")

# ---- Headers ----
shopify_headers = {
    "Content-Type": "application/json",
    "X-Shopify-Access-Token": SHOPIFY_TOKEN,
}

supplier_headers = {
    "X-Shopify-Access-Token": SUPPLIER_TOKEN
}

# ---- Safe request with retries ----
def safe_request(method, url, **kwargs):
    for attempt in range(5):
        try:
            r = requests.request(method, url, timeout=30, **kwargs)
            if r.status_code == 429:  # Shopify rate limit
                retry_after = int(r.headers.get("Retry-After", 2))
                print(f"⚠️ Rate limited. Sleeping for {retry_after} seconds...")
                time.sleep(retry_after)
                continue
            r.raise_for_status()
            return r
        except requests.exceptions.RequestException as e:
            print(f"⚠️ Request failed ({e}). Attempt {attempt+1}/5")
            time.sleep(2**attempt)  # exponential backoff
    raise Exception(f"❌ Failed after 5 retries: {url}")

# ---- Fetch supplier products ----
def fetch_supplier_products():
    print("🔹 Fetching supplier products...")
    r = safe_request("GET", SUPPLIER_API_URL, headers=supplier_headers)
    try:
        data = r.json()
    except Exception:
        print("❌ Supplier response not JSON:", r.text)
        sys.exit(1)
    return data.get("products", [])

# ---- Fetch Shopify variants by SKU ----
def fetch_shopify_variants():
    print("🔹 Fetching Shopify variants by SKU...")
    variants_by_sku = {}
    url = f"https://{SHOPIFY_STORE}.myshopify.com/admin/api/2023-10/variants.json?limit=250"
    while url:
        r = safe_request("GET", url, headers=shopify_headers)
        data = r.json()
        for v in data.get("variants", []):
            sku = v.get("sku")
            if sku:
                variants_by_sku[sku] = v
        url = r.links.get("next", {}).get("url")
        if url:
            time.sleep(0.5)  # avoid Shopify rate limit
    print(f"✅ Fetched {len(variants_by_sku)} Shopify variants")
    return variants_by_sku

# ---- Get location ID ----
def get_location_id():
    url = f"https://{SHOPIFY_STORE}.myshopify.com/admin/api/2023-10/locations.json"
    r = safe_request("GET", url, headers=shopify_headers)
    return r.json()["locations"][0]["id"]

# ---- Update price ----
def update_price(variant_id, new_price, sku):
    url = f"https://{SHOPIFY_STORE}.myshopify.com/admin/api/2023-10/variants/{variant_id}.json"
    payload = {"variant": {"id": variant_id, "price": new_price}}
    safe_request("PUT", url, headers=shopify_headers, json=payload)
    print(f"✅ Updated price for SKU {sku} → {new_price:.2f}")
    time.sleep(0.5)

# ---- Update inventory ----
def update_inventory(inventory_item_id, location_id, quantity, sku):
    url = f"https://{SHOPIFY_STORE}.myshopify.com/admin/api/2023-10/inventory_levels/set.json"
    payload = {
        "location_id": location_id,
        "inventory_item_id": inventory_item_id,
        "available": int(quantity)
    }
    safe_request("POST", url, headers=shopify_headers, json=payload)
    print(f"✅ Updated inventory for SKU {sku} → {quantity}")
    time.sleep(0.5)

# ---- Main sync ----
def main():
    shopify_variants = fetch_shopify_variants()
    supplier_products = fetch_supplier_products()
    location_id = get_location_id()

    print(f"🔹 Updating {len(supplier_products)} products from supplier...")
    for product in supplier_products:
        sku = str(product.get("sku"))
        price = product.get("price")
        quantity = product.get("quantity", 0)

        if sku not in shopify_variants:
            continue

        variant = shopify_variants[sku]
        update_price(variant["id"], price, sku)
        update_inventory(variant["inventory_item_id"], location_id, quantity, sku)

    print("✅ Shopify Sync completed!")

if __name__ == "__main__":
    main()
