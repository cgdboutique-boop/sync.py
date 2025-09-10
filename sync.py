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
# Auto-fetch Location ID
# -----------------------------
location_resp = requests.get(f"{SHOP_URL}/locations.json", headers=shopify_headers)
if location_resp.status_code != 200:
    print("Failed to fetch locations:", location_resp.text)
    exit(1)

locations = location_resp.json().get("locations", [])
if not locations:
    print("No locations found in Shopify store.")
    exit(1)

LOCATION_ID = locations[0]["id"]
print(f"Using Location ID: {LOCATION_ID} ({locations[0]['name']})")

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

def extract_sku(text):
    """Extract numeric SKU from supplier title"""
    if not text:
        return None
    match = re.search(r'\b\d+\b', text)
    return match.group(0) if match else None

# -----------------------------
# Fetch Shopify products to prevent duplicates
# -----------------------------
shopify_resp = requests.get(f"{SHOP_URL}/products.json", headers=shopify_headers)
shopify_products = shopify_resp.json().get("products", [])

sku_map = {}
title_map = {}
for sp in shopify_products:
    clean_title = clean_text(sp.get("title", ""))
    for var in sp.get("variants", []):
        sku = var.get("sku")
        if sku:
            sku_map[sku] = {
                "product_id": sp["id"],
                "variant_id": var["id"],
                "inventory_item_id": var["inventory_item_id"]
            }
    title_map[clean_title] = sp["id"]

# -----------------------------
# Fetch Supplier products
# -----------------------------
supplier_resp = requests.get(SUPPLIER_API_URL, headers=supplier_headers)
if supplier_resp.status_code != 200:
    print("Supplier API request failed:", supplier_resp.text)
    exit(1)

supplier_products = supplier_resp.json().get("products", [])

# -----------------------------
# Sync products and inventory
# -----------------------------
for product in supplier_products:
    supplier_sku = extract_sku(product.get("title"))
    if not supplier_sku:
        continue

    # Swap title and body_html
    title = clean_text(product.get("body_html", "No Title"))
    body_html = clean_text(product.get("title", ""))

    images = [{"src": img["src"]} for img in product.get("images", [])] if product.get("images") else []

    supplier_variant = product.get("variants", [{}])[0]
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

    existing_product_id = None
    variant_id = None
    inventory_item_id = None

    # Check by SKU first
    if supplier_sku in sku_map:
        existing_product_id = sku_map[supplier_sku]["product_id"]
        variant_id = sku_map[supplier_sku]["variant_id"]
        inventory_item_id = sku_map[supplier_sku]["inventory_item_id"]

    # Fallback: check by cleaned title
    elif title in title_map:
        existing_product_id = title_map[title]
        # Fetch variant_id & inventory_item_id
        prod_resp = requests.get(f"{SHOP_URL}/products/{existing_product_id}.json", headers=shopify_headers)
        prod_data = prod_resp.json().get("product", {})
        if prod_data.get("variants"):
            variant_id = prod_data["variants"][0]["id"]
            inventory_item_id = prod_data["variants"][0]["inventory_item_id"]

    if existing_product_id:
        # Update product
        resp = requests.put(f"{SHOP_URL}/products/{existing_product_id}.json", headers=shopify_headers, json=payload)
        print(f"Updated product {supplier_sku}: {resp.status_code}")

        # Update inventory
        if inventory_item_id:
            inv_payload = {
                "location_id": LOCATION_ID,
                "inventory_item_id": inventory_item_id,
                "available": supplier_variant.get("inventory_quantity", 0)
            }
            inv_resp = requests.post(f"{SHOP_URL}/inventory_levels/set.json", headers=shopify_headers, json=inv_payload)
            print(f"Updated inventory {supplier_sku}: {inv_resp.status_code}")

    else:
        # Create product
        resp = requests.post(f"{SHOP_URL}/products.json", headers=shopify_headers, json=payload)
        print(f"Created product {supplier_sku}: {resp.status_code}")
