import os
import json
import requests
import argparse

# -------------------------------
# Parse optional --limit argument
# -------------------------------
parser = argparse.ArgumentParser()
parser.add_argument("--limit", type=int, default=None)
args = parser.parse_args()

# -------------------------------
# Load secrets from environment
# -------------------------------
SHOPIFY_STORE = os.environ["SHOPIFY_STORE"]
SHOPIFY_TOKEN = os.environ["SHOPIFY_TOKEN"]
SUPPLIER_API_URL = os.environ["SUPPLIER_API_URL"]
SUPPLIER_TOKEN = os.environ["SUPPLIER_TOKEN"]

# -------------------------------
# Headers
# -------------------------------
supplier_headers = {
    "X-Shopify-Access-Token": SUPPLIER_TOKEN,
    "Accept": "application/json"
}
shopify_headers = {
    "X-Shopify-Access-Token": SHOPIFY_TOKEN,
    "Content-Type": "application/json"
}

# -------------------------------
# Fetch supplier product data
# -------------------------------
supplier_response = requests.get(SUPPLIER_API_URL, headers=supplier_headers)
try:
    supplier_data = supplier_response.json()
except requests.exceptions.JSONDecodeError:
    print("❌ Supplier response is not valid JSON.")
    print(f"Raw response:\n{supplier_response.text[:500]}")
    exit(1)

products = supplier_data.get("products", [])
if args.limit:
    products = products[:args.limit]

success_count = 0
update_count = 0
error_count = 0

# -------------------------------
# Sync each product
# -------------------------------
for product in products:
    handle = product.get("handle", "").strip()
    title = product.get("title", "Untitled Product")
    body_html = product.get("body_html", "")
    vendor = product.get("vendor", "Supplier")
    product_type = product.get("product_type", "")
    tags = product.get("tags", "")
    status = product.get("status", "draft")
    variants = product.get("variants", [])
    images = product.get("images", [])

    # Normalize variants
    for v in variants:
        v["inventory_management"] = "shopify"
        v["inventory_policy"] = "deny"
        v["price"] = v.get("price", "0.00")
        v["inventory_quantity"] = v.get("inventory_quantity", 0)

    # -------------------------------
    # Check if product exists
    # -------------------------------
    check_url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products.json?handle={handle}"
    check_response = requests.get(check_url, headers=shopify_headers)
    existing = check_response.json().get("products", [])

    if existing:
        # Update product
        product_id = existing[0]["id"]
        update_payload = {
            "product": {
                "id": product_id,
                "title": title,
                "body_html": body_html,
                "tags": tags,
                "status": status,
                "variants": variants,
                "images": images
            }
        }
        update_url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products/{product_id}.json"
        response = requests.put(update_url, headers=shopify_headers, data=json.dumps(update_payload))
        if response.status_code == 200:
            print(f"🔄 Updated: {title}")
            update_count += 1
        else:
            print(f"❌ Failed to update: {title} ({response.status_code})")
            print(f"Response: {response.text}")
            error_count += 1
    else:
        # Create new product
        create_payload = {
            "product": {
                "title": title,
                "body_html": body_html,
                "vendor": vendor,
                "product_type": product_type,
                "handle": handle,
                "tags": tags,
                "status": status,
                "variants": variants,
                "images": images
            }
        }
        create_url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products.json"
        response = requests.post(create_url, headers=shopify_headers, data=json.dumps(create_payload))
        if response.status_code == 201:
            print(f"✅ Created: {title}")
            success_count += 1
        else:
            print(f"❌ Failed to create: {title} ({response.status_code})")
            print(f"Response: {response.text}")
            error_count += 1

# -------------------------------
# Summary
# -------------------------------
print("\n📦 Sync Summary")
print(f"✅ Created: {success_count}")
print(f"🔄 Updated: {update_count}")
print(f"❌ Failed: {error_count}")
