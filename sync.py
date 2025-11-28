import os
import json
import requests
from collections import defaultdict, Counter
import re

# ----------------------------
# Load secrets
# ----------------------------
SHOPIFY_STORE = os.environ["SHOPIFY_STORE"]
SHOPIFY_TOKEN = os.environ["SHOPIFY_TOKEN"]
SUPPLIER_API_URL = os.environ["SUPPLIER_API_URL"]
SUPPLIER_TOKEN = os.environ["SUPPLIER_TOKEN"]

# ----------------------------
# Headers
# ----------------------------
supplier_headers = {
    "X-Shopify-Access-Token": SUPPLIER_TOKEN,
    "Accept": "application/json"
}

shopify_headers = {
    "X-Shopify-Access-Token": SHOPIFY_TOKEN,
    "Content-Type": "application/json"
}

# ----------------------------
# Extract clean size from SKU text
# Example handled:
# 1000754 (100)
# 1000754 (100)-4
# 1000754 (120)-Large
# ----------------------------
def extract_size(text):
    if not text:
        return None

    text = str(text)

    # Find characters inside ()
    match = re.search(r"\(([^)]+)\)", text)
    if match:
        return match.group(1).strip()

    return None


# ----------------------------
# Fetch supplier products
# ----------------------------
def fetch_supplier_products(limit=250):
    products = []
    since_id = 0

    while True:
        params = {"limit": limit, "since_id": since_id}
        response = requests.get(SUPPLIER_API_URL, headers=supplier_headers, params=params)

        if response.status_code != 200:
            print(f"❌ Supplier API error (since_id {since_id}): {response.text}")
            break

        data = response.json().get("products", [])
        if not data:
            break

        products.extend(data)
        print(f"📥 Fetched {len(data)} products (since_id: {since_id})")

        since_id = max(p["id"] for p in data)

    print(f"✅ Total supplier products fetched: {len(products)}")
    return products


# ----------------------------
# Main Sync Logic
# ----------------------------
def sync_products():
    supplier_products = fetch_supplier_products()

    sku_groups = defaultdict(list)

    # Group products by base SKU
    for product in supplier_products:
        for v in product.get("variants", []):
            if not isinstance(v, dict):
                continue

            sku = v.get("sku")
            if not isinstance(sku, str):
                continue

            sku_clean = sku.replace("#", "").strip()

            if "(200)" in sku_clean:     # skip discontinued
                continue

            if not sku_clean:
                continue

            base_sku = sku_clean.split(" ")[0].strip()  # before first space

            sku_groups[base_sku].append((product, v))

    synced = []
    vendor_name = "CGD Kids Boutique"

    # Process each SKU group
    for base_sku, items in sku_groups.items():
        print(f"\n🔄 Syncing base SKU: {base_sku}")

        product, _ = items[0]

        # Skip products belonging to other vendors
        if product.get("vendor") != vendor_name:
            print(f"⏭️ Skipped — vendor mismatch: {product.get('vendor')}")
            continue

        # Build product data
        title = product.get("title", "").replace("#", "").strip()
        body_html = product.get("body_html", "")
        product_type = product.get("product_type", "")
        tags = product.get("tags", "")
        status = product.get("status", "active")

        # Clean images
        images = product.get("images", [])
        for img in images:
            if isinstance(img, dict):
                for key in ["id", "product_id", "admin_graphql_api_id", "created_at", "updated_at"]:
                    img.pop(key, None)

        # Build variants
        variants = []
        sizes = []

        for _, v in items:
            sku_val = v.get("sku", "")
            variant_size = extract_size(sku_val)

            if not variant_size:
                print(f"⚠️ Skipping variant — no size extracted: {sku_val}")
                continue

            sizes.append(variant_size)

            variant = {
                "sku": sku_val.replace("#", "").strip(),
                "option1": variant_size,
                "price": v.get("price", "0.00"),
                "inventory_management": "shopify",
                "inventory_policy": "deny",
                "inventory_quantity": v.get("inventory_quantity", 0)
            }

            variants.append(variant)

        if not variants:
            print(f"⚠️ No valid variants for {base_sku}, skipping...")
            continue

        # Build product handle
        handle = base_sku.lower().strip()

        payload = {
            "product": {
                "title": title,
                "body_html": body_html,
                "vendor": vendor_name,
                "product_type": product_type,
                "handle": handle,
                "tags": tags,
                "status": status,
                "options": [{"name": "Size", "values": sizes}],
                "variants": variants,
                "images": images
            }
        }

        # Check if Shopify product exists
        check_url = (
            f"https://{SHOPIFY_STORE}/admin/api/2025-07/products.json?handle={handle}"
        )
        check = requests.get(check_url, headers=shopify_headers).json()
        existing_products = check.get("products", [])

        # Update existing
        if existing_products:
            shopify_id = existing_products[0]["id"]
            payload["product"]["id"] = shopify_id

            url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products/{shopify_id}.json"
            print(f"🔄 Updating product: {handle}")
            response = requests.put(url, headers=shopify_headers, data=json.dumps(payload))

        # Create new
        else:
            url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products.json"
            print(f"🆕 Creating product: {handle}")
            response = requests.post(url, headers=shopify_headers, data=json.dumps(payload))

        # Log Shopify response
        try:
            print(json.dumps(response.json(), indent=2))
        except:
            print(response.text)

        if response.status_code in [200, 201]:
            print(f"✅ Synced: {handle}")
            synced.append(handle)
        else:
            print(f"❌ Failed to sync {handle}: {response.status_code}")

    # Duplicate report
    print("\n📊 Duplicate Check Report")
    for handle, count in Counter(synced).items():
        if count > 1:
            print(f"⚠️ Duplicate detected: {handle} synced {count} times")


# ----------------------------
# Run
# ----------------------------
if __name__ == "__main__":
    sync_products()
