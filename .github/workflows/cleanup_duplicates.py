import os
import time
import requests
from collections import defaultdict

# ----------------------------
# Load secrets
# ----------------------------
SHOPIFY_STORE = os.environ["SHOPIFY_STORE"]
SHOPIFY_TOKEN = os.environ["SHOPIFY_TOKEN"]

shopify_headers = {
    "X-Shopify-Access-Token": SHOPIFY_TOKEN,
    "Content-Type": "application/json"
}

# ----------------------------
# Fetch all products (paginated)
# ----------------------------
def fetch_all_products(limit=250):
    products = []
    page_info = None
    base_url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products.json"

    while True:
        params = {"limit": limit}
        if page_info:
            params["page_info"] = page_info

        response = requests.get(base_url, headers=shopify_headers, params=params)
        if response.status_code != 200:
            print(f"❌ Failed to fetch products: {response.text}")
            break

        data = response.json().get("products", [])
        if not data:
            break

        products.extend(data)

        # Look for pagination link
        link_header = response.headers.get("Link", "")
        if 'rel="next"' in link_header:
            # Extract page_info from link
            try:
                page_info = link_header.split("page_info=")[1].split(">")[0]
            except Exception:
                break
        else:
            break

        print(f"📥 Fetched {len(data)} products, total so far {len(products)}")

    print(f"✅ Total products fetched: {len(products)}")
    return products

# ----------------------------
# Delete duplicates by handle
# ----------------------------
def delete_duplicates(products):
    grouped = defaultdict(list)
    for p in products:
        grouped[p["handle"]].append(p)

    total_deleted = 0
    for handle, items in grouped.items():
        if len(items) > 1:
            # Sort by created_at → keep latest, delete older
            items.sort(key=lambda x: x["created_at"], reverse=True)
            to_delete = items[1:]  # keep first one

            for prod in to_delete:
                prod_id = prod["id"]
                url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products/{prod_id}.json"
                response = requests.delete(url, headers=shopify_headers)

                if response.status_code == 200:
                    print(f"🗑️ Deleted duplicate {handle} (ID {prod_id})")
                    total_deleted += 1
                else:
                    print(f"❌ Failed to delete {handle} (ID {prod_id}): {response.text}")

                # Avoid hitting Shopify API limits
                time.sleep(0.6)

    print(f"✅ Cleanup complete. Total duplicates deleted: {total_deleted}")

# ----------------------------
# Run cleanup
# ----------------------------
if __name__ == "__main__":
    products = fetch_all_products()
    delete_duplicates(products)
