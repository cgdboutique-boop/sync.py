import os
import time
import requests

# =============================
# Shopify + Supplier Setup
# =============================

SHOPIFY_STORE = "cgdboutique"
SHOPIFY_API_VERSION = "2023-10"
SHOPIFY_TOKEN = os.getenv("SHOPIFY_TOKEN")

SUPPLIER_API_URL = os.getenv("SUPPLIER_API_URL")
SUPPLIER_TOKEN = os.getenv("SUPPLIER_TOKEN")

shopify_headers = {
    "Content-Type": "application/json",
    "X-Shopify-Access-Token": SHOPIFY_TOKEN,
}

supplier_headers = {"Authorization": f"Bearer {SUPPLIER_TOKEN}"}


# =============================
# Helper: Safe request with retry
# =============================

def safe_request(method, url, **kwargs):
    retries = 5
    backoff = 2
    for attempt in range(retries):
        try:
            r = requests.request(method, url, timeout=30, **kwargs)
            if r.status_code == 429:  # Rate limit hit
                retry_after = int(r.headers.get("Retry-After", 2))
                print(f"Rate limit hit. Sleeping {retry_after}s...")
                time.sleep(retry_after)
                continue
            r.raise_for_status()
            return r
        except requests.exceptions.RequestException as e:
            print(f"⚠️ Request failed ({e}). Attempt {attempt+1}/{retries}")
            time.sleep(backoff)
            backoff *= 2
    raise Exception(f"Failed after {retries} retries: {url}")


# =============================
# Fetch supplier products
# =============================

def fetch_supplier_products():
    r = safe_request("GET", SUPPLIER_API_URL, headers=supplier_headers)
    return r.json()


# =============================
# Fetch Shopify variants (cursor pagination)
# =============================

def fetch_shopify_variants():
    variants_by_sku = {}
    base_url = f"https://{SHOPIFY_STORE}.myshopify.com/admin/api/{SHOPIFY_API_VERSION}/variants.json?limit=250"

    next_page = base_url
    while next_page:
        r = safe_request("GET", next_page, headers=shopify_headers)
        data = r.json()
        variants = data.get("variants", [])

        for v in variants:
            if v.get("sku"):
                variants_by_sku[v["sku"]] = v

        # Check for pagination in Link header
        link = r.headers.get("Link")
        next_page = None
        if link and 'rel="next"' in link:
            for part in link.split(","):
                if 'rel="next"' in part:
                    next_page = part.split(";")[0].strip(" <>")

    print(f"✅ Fetched {len(variants_by_sku)} Shopify variants by SKU")
    return variants_by_sku


# =============================
# Fetch location ID
# =============================

def get_location_id():
    url = f"https://{SHOPIFY_STORE}.myshopify.com/admin/api/{SHOPIFY_API_VERSION}/locations.json"
    r = safe_request("GET", url, headers=shopify_headers)
    return r.json()["locations"][0]["id"]


# =============================
# Update price
# =============================

def update_price(variant_id, new_price, sku):
    url = f"https://{SHOPIFY_STORE}.myshopify.com/admin/api/{SHOPIFY_API_VERSION}/variants/{variant_id}.json"
    payload = {"variant": {"id": variant_id, "price": new_price}}
    r = safe_request("PUT", url, headers=shopify_headers, json=payload)
    print(f"💰 Updated price for variant {variant_id} (SKU {sku}) → {new_price}")


# =============================
# Update inventory
# =============================

def update_inventory(inventory_item_id, location_id, target_quantity, sku):
    url = f"https://{SHOPIFY_STORE}.myshopify.com/admin/api/{SHOPIFY_API_VERSION}/inventory_levels/set.json"
    payload = {
        "location_id": location_id,
        "inventory_item_id": inventory_item_id,
        "available": int(target_quantity),
    }
    r = safe_request("POST", url, headers=shopify_headers, json=payload)
    print(f"📦 Set inventory for {inventory_item_id} (SKU {sku}) → {target_quantity}")


# =============================
# Main sync
# =============================

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

        if sku not in shopify_variants:
            continue

        variant = shopify_variants[sku]
        variant_id = variant["id"]
        inventory_item_id = variant["inventory_item_id"]

        # Update price
        if str(variant.get("price")) != str(price):
            update_price(variant_id, price, sku)

        # Update inventory (avoid duplicate updates)
        if inventory_item_id not in seen_inventory_items:
            update_inventory(inventory_item_id, location_id, quantity, sku)
            seen_inventory_items.add(inventory_item_id)
        else:
            print(f"⏩ Skipping duplicate inventory update for {inventory_item_id}")


if __name__ == "__main__":
    main()
