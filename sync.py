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
    "Authorization": f"Bearer {SUPPLIER_TOKEN}",
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
if supplier_response.status_code != 200:
    print(f"❌ Failed to fetch supplier data: {supplier_response.status_code}")
    print(supplier_response.text)
    exit(1)

supplier_data = supplier_response.json()
items = supplier_data.get("data", {}).get("items", [])
if args.limit:
    items = items[:args.limit]

success_count = 0
update_count = 0
error_count = 0

# -------------------------------
# Sync each product
# -------------------------------
for item in items:
    attributes = item.get("attributes", {})

    handle = attributes.get("handle", "").strip()
    title = attributes.get("title", "Untitled Product")
    body_html = attributes.get("description", "")
    vendor = attributes.get("vendor", "Supplier")
    product_type = attributes.get("product_type", "")
    tags = attributes.get("tags", "")
    status = attributes.get("status", "draft")

    # -------------------------------
    # Build options + variants
    # -------------------------------
    option_names = []
    variants = []

    if "variants" in attributes and isinstance(attributes["variants"], list) and attributes["variants"]:
        # Collect all option names used
        for v in attributes["variants"]:
            if "options" in v:
                for opt_name in v["options"].keys():
                    if opt_name not in option_names and len(option_names) < 3:
                        option_names.append(opt_name)

        # Build variants with option mapping
        for v in attributes["variants"]:
            variant = {
                "sku": v.get("sku", ""),
                "price": v.get("price", "0.00"),
                "inventory_quantity": v.get("inventory_quantity", 0),
                "inventory_management": "shopify",
                "inventory_policy": "deny"
            }

            # Map option values (up to 3)
            if "options" in v:
                for idx, opt_name in enumerate(option_names, start=1):
                    variant[f"option{idx}"] = v["options"].get(opt_name, "Default")
            else:
                variant["option1"] = "Default Title"

            variants.append(variant)
    else:
        # fallback to single-variant model
        option_names = ["Title"]
        variants = [{
            "sku": attributes.get("sku", ""),
            "price": attributes.get("price", "0.00"),
            "option1": "Default Title",
            "inventory_quantity": attributes.get("inventory_quantity", 0),
            "inventory_management": "shopify",
            "inventory_policy": "deny"
        }]

    # Shopify product options structure
    options = [{"name": name} for name in option_names]

    # -------------------------------
    # Build images
    # -------------------------------
    images = []
    for img in attributes.get("images", []):
        if "src" in img:
            images.append({"src": img["src"]})

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
                "options": options,
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
                "options": options,
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
