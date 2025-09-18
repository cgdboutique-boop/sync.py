import os
import requests
import argparse
from collections import defaultdict

# -------------------------------
# CONFIG
# -------------------------------
SHOPIFY_STORE = os.environ.get("SHOPIFY_STORE")
SHOPIFY_TOKEN = os.environ.get("SHOPIFY_TOKEN")

HEADERS = {
    "Content-Type": "application/json",
    "X-Shopify-Access-Token": SHOPIFY_TOKEN,
}

API_BASE = f"https://{SHOPIFY_STORE}/admin/api/2025-01"


# -------------------------------
# Shopify Helpers
# -------------------------------
def get_all_products():
    """Fetch all products from Shopify (REST pagination)."""
    products = []
    url = f"{API_BASE}/products.json?limit=250"
    while url:
        resp = requests.get(url, headers=HEADERS)
        resp.raise_for_status()
        data = resp.json().get("products", [])
        products.extend(data)

        # Pagination
        link = resp.headers.get("Link")
        if link and 'rel="next"' in link:
            url = link.split(";")[0].strip("<> ")
        else:
            url = None
    return products


def update_vendor(product_id, new_vendor):
    """Update product vendor."""
    url = f"{API_BASE}/products/{product_id}.json"
    payload = {"product": {"id": product_id, "vendor": new_vendor}}
    resp = requests.put(url, headers=HEADERS, json=payload)
    if resp.status_code == 200:
        print(f"✅ Updated vendor for product {product_id} → {new_vendor}")
        return True
    else:
        print(f"❌ Failed to update vendor for product {product_id}: {resp.text}")
        return False


def delete_product(product_id):
    """Delete product by ID."""
    url = f"{API_BASE}/products/{product_id}.json"
    resp = requests.delete(url, headers=HEADERS)
    if resp.status_code == 200:
        print(f"🗑️ Deleted duplicate product {product_id}")
        return True
    else:
        print(f"❌ Failed to delete product {product_id}: {resp.text}")
        return False


# -------------------------------
# Main Logic
# -------------------------------
def clean_and_update():
    products = get_all_products()
    print(f"📦 Total products fetched: {len(products)}")

    updated_count = 0
    deleted_count = 0

    # --- Step 1: Update vendor for all products
    for p in products:
        if p.get("vendor") != "CGD Kids Boutique":
            if update_vendor(p["id"], "CGD Kids Boutique"):
                updated_count += 1

    # --- Step 2: Remove duplicates by handle
    grouped = defaultdict(list)
    for p in products:
        grouped[p["handle"]].append(p)

    for handle, group in grouped.items():
        if len(group) > 1:
            # Sort by created_at → keep oldest
            group.sort(key=lambda x: x["created_at"])
            to_keep = group[0]
            to_delete = group[1:]
            for d in to_delete:
                if delete_product(d["id"]):
                    deleted_count += 1
            print(f"🔄 Handle '{handle}': kept {to_keep['id']}, deleted {len(to_delete)} duplicates")

    # --- Report
    print("\n📊 SUMMARY")
    print(f"   ✅ Vendor updates: {updated_count}")
    print(f"   🗑️ Duplicates removed: {deleted_count}")
    print(f"   📦 Final total products (approx): {len(products) - deleted_count}")


# -------------------------------
# CLI
# -------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    args = parser.parse_args()
    clean_and_update()
