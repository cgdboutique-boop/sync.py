import os
import time
import json
import requests
from collections import defaultdict

# ----------------------------
# Load secrets from environment
# ----------------------------
SHOPIFY_STORE = os.environ["SHOPIFY_STORE"]
SHOPIFY_TOKEN = os.environ["SHOPIFY_TOKEN"]

# ----------------------------
# Headers
# ----------------------------
shopify_headers = {
    "X-Shopify-Access-Token": SHOPIFY_TOKEN,
    "Content-Type": "application/json"
}

# ----------------------------
# Fetch all Shopify products by vendor
# ----------------------------
def fetch_shopify_products_by_vendor(vendor_name, limit=250):
    print(f"📦 Fetching products for vendor: {vendor_name}")
    all_products = []
    page_info = None

    while True:
        url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products.json?vendor={vendor_name}&limit={limit}"
        if page_info:
            url += f"&page_info={page_info}"
        response = requests.get(url, headers=shopify_headers)
        if response.status_code != 200:
            print(f"❌ Error fetching products: {response.text}")
            break
        data = response.json().get("products", [])
        all_products.extend(data)
        print(f"📥 Fetched {len(data)} products (total: {len(all_products)})")

        # Pagination header check
        link_header = response.headers.get("Link", "")
        if 'rel="next"' not in link_header:
            break
        try:
            page_info = link_header.split("page_info=")[1].split(">")[0]
        except:
            break

        time.sleep(0.5)

    print(f"✅ Total products fetched for vendor '{vendor_name}': {len(all_products)}")
    return all_products

# ----------------------------
# Delete product from Shopify
# ----------------------------
def delete_product(product_id, title):
    url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products/{product_id}.json"
    response = requests.delete(url, headers=shopify_headers)
    if response.status_code == 200:
        print(f"🗑️ Deleted duplicate: {title} (ID: {product_id})")
    else:
        print(f"❌ Failed to delete {title} (ID: {product_id}) — {response.text}")

# ----------------------------
# Main duplicate cleanup logic
# ----------------------------
def cleanup_duplicates(vendor_name="CGD Kids Boutique"):
    products = fetch_shopify_products_by_vendor(vendor_name)

    if not products:
        print("⚠️ No products found for this vendor.")
        return

    handle_map = defaultdict(list)
    sku_map = defaultdict(list)

    # Group by handle and SKU
    for product in products:
        handle = product.get("handle", "").strip().lower()
        handle_map[handle].append(product)
        for variant in product.get("variants", []):
            sku = variant.get("sku", "").strip()
            if sku:
                sku_map[sku].append(product)

    # ----------------------------
    # Check for duplicate handles
    # ----------------------------
    print("\n🔍 Checking for duplicate handles...")
    for handle, items in handle_map.items():
        if len(items) > 1:
            sorted_items = sorted(items, key=lambda x: x.get("updated_at", ""), reverse=True)
            keep = sorted_items[0]
            delete_list = sorted_items[1:]
            print(f"⚠️ Handle duplicate found: {handle} — keeping {keep['id']} and deleting {len(delete_list)} others")
            for item in delete_list:
                delete_product(item["id"], item["title"])
                time.sleep(0.7)

    # ----------------------------
    # Check for duplicate SKUs
    # ----------------------------
    print("\n🔍 Checking for duplicate SKUs...")
    for sku, items in sku_map.items():
        if len(items) > 1:
            # Remove duplicates that aren't already deleted
            unique_items = {p["id"]: p for p in items}.values()
            sorted_items = sorted(unique_items, key=lambda x: x.get("updated_at", ""), reverse=True)
            keep = sorted_items[0]
            delete_list = sorted_items[1:]
            print(f"⚠️ SKU duplicate found: {sku} — keeping {keep['id']} and deleting {len(delete_list)} others")
            for item in delete_list:
                delete_product(item["id"], item["title"])
                time.sleep(0.7)

    print("\n✅ Duplicate cleanup complete for vendor:", vendor_name)

# ----------------------------
# Run cleanup
# ----------------------------
if __name__ == "__main__":
    cleanup_duplicates("CGD Kids Boutique")
