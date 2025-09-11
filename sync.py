import os
import requests
import time

# Shopify API setup
SHOPIFY_STORE = "cgdboutique"
SHOPIFY_API_VERSION = "2023-10"
SHOPIFY_TOKEN = os.environ.get("SHOPIFY_TOKEN")  # ✅ use GitHub secret

shopify_headers = {
    "Content-Type": "application/json",
    "X-Shopify-Access-Token": SHOPIFY_TOKEN,
}

# Supplier API setup
SUPPLIER_API_URL = os.environ.get("SUPPLIER_API_URL")  # ✅ use GitHub secret
SUPPLIER_TOKEN = os.environ.get("SUPPLIER_TOKEN")      # ✅ use GitHub secret
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
            time.sleep(2**attempt)
    raise Exception(f"Failed after 5 retries: {url}")

# ---- Fetch supplier products ----
def fetch_supplier_products():
    r = safe_request("GET", SUPPLIER_API_URL, headers=supplier_headers)
    return r.json()

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

        url = r.links.get("next", {}).get("url")  # pagination

    print(f"✅ Fetched {len(variants_by_sku)} Shopify variants by SKU")
    return variants_by_sku

# ---- Get location ID ----
def get_location_id():
    url = f"https://{SHOPIFY_STORE}.myshopify.com/admin/api/{SHOPIFY_API_VERSION}/locations.json"
    r = safe_request("GET", url, headers=shopify_headers)
    return r.json()["locations"][0]["id"]

# ---- Update price ----
def update_price(variant_id, new_price, sku):
    url = f"https://{SHOPIFY_STORE}.myshopify.com/admin/api/{SHOPIFY_API_VERSION}/variants/{variant_id}.json"
    payload = {"variant": {"id": variant_id, "price": new_price}}
    r = safe_request("PUT", url, headers=shopify_headers, json=payload)
    print(f"✅ Updated price for variant {variant_id} (SKU {sku}) → {new_price:.2f}")

# ---- Update inventory ----
def update_inventory(inventory_item_id, location_id, quantity, sku):
    url = f"https://{SHOPIFY_STORE}.myshopify.com/admin/api/{SHOPIFY_API_VERSION}/inventory_levels/set.json"
    payload = {"location_id": location_id, "inventory_item_id": inventory_item_id, "available": int(quantity)}
    r = safe_request("POST", url, headers=shopify_headers, json=payload)
    print(f"✅ Inventory for item {inventory_item_id} (SKU {sku}) set to {quantity}")

# ---- Main sync ----
def main():
    shopify_variants = fetch_shopify_variants()
    supplier_products = fetch_supplier_products()
    location_id = get_location_id()
    print(f"✅ Fetched {len(supplier_products)} supplier products")

    for product in supplier_products:
        sku = str(product.get("sku"))
        price = product.get("price")
        quantity = product.get("quantity", 0)

        if sku not in shopify_variants:
            continue

        variant = shopify_variants[sku]
        variant_id = variant["id"]
        inventory_item_id = variant["inventory_item_id"]

        if str(variant.get("price")) != str(price):
            update_price(variant_id, price, sku)

        update_inventory(inventory_item_id, location_id, quantity, sku)

if __name__ == "__main__":
    main()
