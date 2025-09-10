import requests
import os

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
# Get Shopify Location ID
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

# Map existing Shopify variants by SKU
sku_to_variant = {}
for product in shopify_products:
    for variant in product.get("variants", []):
        sku = variant.get("sku")
        if sku:
            sku_to_variant[sku] = variant

# -----------------------------
# Fetch Supplier Products
# -----------------------------
supplier_resp = requests.get(SUPPLIER_API_URL, headers=supplier_headers)
supplier_resp.raise_for_status()
supplier_products = supplier_resp.json().get("products", [])

# -----------------------------
# Update Inventory
# -----------------------------
for product in supplier_products:
    supplier_variant = product.get("variants", [{}])[0]
    sku = supplier_variant.get("sku")
    quantity = supplier_variant.get("inventory_quantity", 0)

    if sku in sku_to_variant:
        shopify_variant = sku_to_variant[sku]
        inventory_item_id = shopify_variant.get("inventory_item_id")

        if inventory_item_id:
            inv_payload = {
                "location_id": LOCATION_ID,
                "inventory_item_id": inventory_item_id,
                "available": quantity
            }
            inv_resp = requests.post(f"{SHOP_URL}/inventory_levels/set.json", headers=shopify_headers, json=inv_payload)
            print(f"Updated SKU {sku} inventory to {quantity}: {inv_resp.status_code}")
        else:
            print(f"No inventory_item_id for SKU {sku}")
    else:
        print(f"SKU {sku} not found in Shopify, skipping")
