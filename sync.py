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

# -----------------------------
# Fetch existing Shopify products by SKU
# -----------------------------
shopify_products = []
page = 1
while True:
    resp = requests.get(f"{SHOP_URL}/products.json", headers=shopify_headers, params={"limit": 250, "page": page})
    if resp.status_code != 200:
        print("Error fetching Shopify products:", resp.text)
        exit(1)
    batch = resp.json().get("products", [])
    if not batch:
        break
    shopify_products.extend(batch)
    page += 1

sku_map = {}
for sp in shopify_products:
    for var in sp.get("variants", []):
        sku = var.get("sku")
        if sku:
            sku_map[sku] = {
                "product_id": sp["id"],
                "variant_id": var["id"],
                "inventory_item_id": var["inventory_item_id"]
            }

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
    supplier_variant = product.get("variants", [{}])[0]
    supplier_sku = supplier_variant.get("sku")
    if not supplier_sku:
        continue

    # Swap title and body_html
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

    if supplier_sku in sku_map:
        # Update existing product
        existing = sku_map[supplier_sku]
        product_id = existing["product_id"]
        variant_id = existing["variant_id"]
        inventory_item_id = existing["inventory_item_id"]

        resp = requests.put(f"{SHOP_URL}/products/{product_id}.json", headers=shopify_headers, json=payload)
        print(f"Updated product {supplier_sku}: {resp.status_code}")

        # Update inventory
        inv_payload = {
            "location_id": LOCATION_ID,
            "inventory_item_id": inventory_item_id,
            "available": supplier_variant.get("inventory_quantity", 0)
        }
        inv_resp = requests.post(f"{SHOP_URL}/inventory_levels/set.json", headers=shopify_headers, json=inv_payload)
        print(f"Inventory synced {supplier_sku}: {inv_resp.status_code}")

    else:
        # Create new product
        resp = requests.post(f"{SHOP_URL}/products.json", headers=shopify_headers, json=payload)
        print(f"Created product {supplier_sku}: {resp.status_code}")
