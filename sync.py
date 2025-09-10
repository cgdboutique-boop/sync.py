import requests
import os
import re

# -----------------------------
# Configuration
# -----------------------------
SUPPLIER_API_URL = "https://the-brave-ones-childrens-fashion.myshopify.com/admin/api/2023-10/products.json"
SUPPLIER_TOKEN = os.getenv("SUPPLIER_TOKEN")

SHOP_URL = "https://cgdboutique.myshopify.com/admin/api/2023-10"
SHOPIFY_TOKEN = os.getenv("SHOPIFY_TOKEN")

shopify_headers = {"X-Shopify-Access-Token": SHOPIFY_TOKEN, "Content-Type": "application/json"}
supplier_headers = {"X-Shopify-Access-Token": SUPPLIER_TOKEN}

# -----------------------------
# Helper Functions
# -----------------------------
def clean_text(text):
    if not text:
        return ""
    text = re.sub(r"<\/?p>", "", text)
    text = re.sub(r"Â", "", text)
    text = re.sub(r"<\/?span.*?>", "", text)
    text = re.sub(r'data-mce-fragment="1"', "", text)
    return text.strip()

# -----------------------------
# Fetch Shopify Location ID
# -----------------------------
location_resp = requests.get(f"{SHOP_URL}/locations.json", headers=shopify_headers)
location_resp.raise_for_status()
locations = location_resp.json().get("locations", [])
LOCATION_ID = locations[0]["id"] if locations else None
print(f"Using Location ID: {LOCATION_ID}")

# -----------------------------
# Fetch all Shopify products
# -----------------------------
shopify_products = []
page = 1
while True:
    resp = requests.get(f"{SHOP_URL}/products.json", headers=shopify_headers, params={"limit": 250, "page": page})
    resp.raise_for_status()
    batch = resp.json().get("products", [])
    if not batch:
        break
    shopify_products.extend(batch)
    page += 1

# Map existing products by SKU and handle
sku_to_product = {}
handle_to_product = {}
for product in shopify_products:
    handle_to_product[product["handle"]] = product
    for variant in product.get("variants", []):
        sku = variant.get("sku")
        if sku:
            sku_to_product[sku] = product

# -----------------------------
# Fetch Supplier Products
# -----------------------------
supplier_resp = requests.get(SUPPLIER_API_URL, headers=supplier_headers)
supplier_resp.raise_for_status()
supplier_products = supplier_resp.json().get("products", [])

# -----------------------------
# Sync Supplier Products
# -----------------------------
for product in supplier_products:
    supplier_variant = product.get("variants", [{}])[0]
    supplier_sku = supplier_variant.get("sku")

    # Swap title/body_html
    title = clean_text(product.get("body_html", "No Title"))
    body_html = clean_text(product.get("title", ""))

    images = [{"src": img["src"]} for img in product.get("images", [])] if product.get("images") else []

    variant_payload = [{
        "option1": "Default",
        "sku": supplier_sku,
        "price": supplier_variant.get("price", "0.00"),
        "inventory_quantity": supplier_variant.get("inventory_quantity", 0),
        "inventory_management": "shopify",
        "inventory_policy": "deny"
    }]

    payload = {
        "product": {
            "title": title,
            "body_html": body_html,
            "vendor": "",
            "product_type": product.get("product_type", ""),
            "tags": product.get("tags", ""),
            "variants": variant_payload,
            "images": images,
            "published": True
        }
    }

    existing_product = None
    if supplier_sku and supplier_sku in sku_to_product:
        existing_product = sku_to_product[supplier_sku]
    elif product.get("handle") and product["handle"] in handle_to_product:
        existing_product = handle_to_product[product["handle"]]

    if existing_product:
        # Update existing product
        product_id = existing_product["id"]
        resp = requests.put(f"{SHOP_URL}/products/{product_id}.json", headers=shopify_headers, json=payload)
        print(f"Updated product {supplier_sku or product['handle']}: {resp.status_code}")

        # Update inventory
        for variant in existing_product.get("variants", []):
            if variant.get("sku") == supplier_sku:
                inv_payload = {
                    "location_id": LOCATION_ID,
                    "inventory_item_id": variant["inventory_item_id"],
                    "available": supplier_variant.get("inventory_quantity", 0)
                }
                inv_resp = requests.post(f"{SHOP_URL}/inventory_levels/set.json", headers=shopify_headers, json=inv_payload)
                print(f"Inventory synced {supplier_sku}: {inv_resp.status_code}")

    else:
        # Create new product
        resp = requests.post(f"{SHOP_URL}/products.json", headers=shopify_headers, json=payload)
        print(f"Created product {supplier_sku or title}: {resp.status_code}")

        # Fetch created variant to update inventory
        created_product = resp.json().get("product", {})
        created_variant = created_product.get("variants", [{}])[0]
        inventory_item_id = created_variant.get("inventory_item_id")
        if inventory_item_id:
            inv_payload = {
                "location_id": LOCATION_ID,
                "inventory_item_id": inventory_item_id,
                "available": supplier_variant.get("inventory_quantity", 0)
            }
            inv_resp = requests.post(f"{SHOP_URL}/inventory_levels/set.json", headers=shopify_headers, json=inv_payload)
            print(f"Inventory synced for new product {supplier_sku}: {inv_resp.status_code}")
