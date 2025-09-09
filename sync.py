import requests
import os
import re

# ---------------- Supplier API ----------------
SUPPLIER_API_URL = "https://the-brave-ones-childrens-fashion.myshopify.com/admin/api/2023-10/products.json"
SUPPLIER_TOKEN = os.getenv("SUPPLIER_TOKEN")

supplier_headers = {"X-Shopify-Access-Token": SUPPLIER_TOKEN}
supplier_response = requests.get(SUPPLIER_API_URL, headers=supplier_headers)

if supplier_response.status_code != 200:
    print("Supplier API request failed:", supplier_response.text)
    exit(1)

supplier_products = supplier_response.json().get("products", [])

# ---------------- Shopify API ----------------
SHOP_URL = "https://cgdboutique.myshopify.com/admin/api/2023-10/products.json"
SHOPIFY_TOKEN = os.getenv("SHOPIFY_TOKEN")
shopify_headers = {
    "X-Shopify-Access-Token": SHOPIFY_TOKEN,
    "Content-Type": "application/json"
}

# ---------------- Location ID for inventory ----------------
LOCATION_ID = 79714615616  # Replace with your Shopify Location ID

# ---------------- Cleaning Function ----------------
def clean_text(text):
    if not text:
        return ""
    text = re.sub(r"<\/?p>", "", text)
    text = re.sub(r"Â", "", text)
    text = re.sub(r"<\/?span.*?>", "", text)
    text = re.sub(r'data-mce-fragment="1"', "", text)
    return text.strip()

# ---------------- Step 1: Fetch existing Shopify products ----------------
all_products = []
page_info = None

while True:
    params = {"limit": 250}
    if page_info:
        params["page_info"] = page_info
    response = requests.get(SHOP_URL, headers=shopify_headers, params=params)
    products = response.json().get("products", [])
    all_products.extend(products)
    # Pagination
    if "Link" in response.headers and 'rel="next"' in response.headers["Link"]:
        page_info = response.headers["Link"].split("page_info=")[1].split(">")[0]
    else:
        break

# Map SKUs to product IDs
sku_map = {}
for product in all_products:
    for variant in product.get("variants", []):
        sku = variant.get("sku")
        if sku:
            if sku in sku_map:
                # Mark duplicate for deletion
                sku_map[sku].append(product["id"])
            else:
                sku_map[sku] = [product["id"]]

# ---------------- Step 2: Delete duplicates ----------------
for sku, ids in sku_map.items():
    if len(ids) > 1:
        # Keep first, delete the rest
        for duplicate_id in ids[1:]:
            del_url = f"https://cgdboutique.myshopify.com/admin/api/2023-10/products/{duplicate_id}.json"
            del_resp = requests.delete(del_url, headers=shopify_headers)
            print(f"Deleted duplicate product {duplicate_id} for SKU {sku}: {del_resp.status_code}")

# ---------------- Step 3: Sync Supplier Products ----------------
for product in supplier_products:
    variants = []
    for variant in product.get("variants", []):
        variants.append({
            "option1": variant.get("option1", ""),
            "sku": variant.get("sku", ""),
            "inventory_quantity": variant.get("inventory_quantity", 0),
            "price": variant.get("price", "0.00"),
            "inventory_management": "shopify",
            "inventory_policy": "deny"
        })

    images = [{"src": img["src"]} for img in product.get("images", [])] if product.get("images") else []

    # Swap supplier title/body
    title = clean_text(product.get("body_html", "No Title"))
    body_html = clean_text(product.get("title", ""))

    payload = {
        "product": {
            "title": title,
            "body_html": body_html,
            "vendor": "",  # remove vendor
            "product_type": product.get("product_type", ""),
            "tags": product.get("tags", ""),
            "variants": variants,
            "images": images,
            "published": True
        }
    }

    # Check if SKU exists
    existing_product = None
    for sku, ids in sku_map.items():
        for variant in product.get("variants", []):
            if variant.get("sku") == sku:
                existing_product = ids[0]
                break
        if existing_product:
            break

    if existing_product:
        # Update existing product
        update_url = f"https://cgdboutique.myshopify.com/admin/api/2023-10/products/{existing_product}.json"
        response = requests.put(update_url, headers=shopify_headers, json=payload)
        print(f"Updated product {existing_product}: {response.status_code}")
    else:
        # Create new product
        response = requests.post(SHOP_URL, headers=shopify_headers, json=payload)
        created_product = response.json().get("product", {})
        print(f"Created product {created_product.get('id', 'Unknown')}: {response.status_code}")

    # ---------------- Step 4: Sync Inventory ----------------
    for variant in product.get("variants", []):
        inventory_item_id = variant.get("inventory_item_id")
        if not inventory_item_id and created_product:
            # Fetch variant ID from Shopify if new product
            created_variant = created_product.get("variants", [{}])[0]
            inventory_item_id = created_variant.get("inventory_item_id")

        if inventory_item_id:
            inventory_url = "https://cgdboutique.myshopify.com/admin/api/2023-10/inventory_levels/set.json"
            inventory_payload = {
                "location_id": LOCATION_ID,
                "inventory_item_id": inventory_item_id,
                "available": variant.get("inventory_quantity", 0)
            }
            inv_response = requests.post(inventory_url, headers=shopify_headers, json=inventory_payload)
            print(f"Inventory Sync for SKU {variant.get('sku')}: {inv_response.status_code}")
