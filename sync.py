import requests
import os
import re
import csv

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
# Location ID for inventory
# -----------------------------
location_resp = requests.get(f"{SHOP_URL}/locations.json", headers=shopify_headers)
location_resp.raise_for_status()
locations = location_resp.json().get("locations", [])
LOCATION_ID = locations[0]["id"] if locations else None
print(f"Using Location ID: {LOCATION_ID}")

# -----------------------------
# Clean text function
# -----------------------------
def clean_text(text):
    if not text:
        return ""
    text = re.sub(r"<\/?p>", "", text)
    text = re.sub(r"Â", "", text)
    text = re.sub(r"<\/?span.*?>", "", text)
    text = re.sub(r"data-mce-fragment=\"1\"", "", text)
    return text.strip()

# -----------------------------
# Fetch Shopify products
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

# Map variants by SKU
sku_to_variant = {}
for product in shopify_products:
    for variant in product.get("variants", []):
        sku = variant.get("sku", "").strip()
        if sku:
            sku_to_variant[sku] = variant

# -----------------------------
# Fetch Supplier Products
# -----------------------------
supplier_resp = requests.get(SUPPLIER_API_URL, headers=supplier_headers)
supplier_resp.raise_for_status()
supplier_products = supplier_resp.json().get("products", [])

# Open CSV log
with open("inventory_update_log.csv", "w", newline="") as csvfile:
    fieldnames = ["sku", "status", "message"]
    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
    writer.writeheader()

    # -----------------------------
    # Sync products
    # -----------------------------
    for product in supplier_products:
        title = clean_text(product.get("body_html", "No Title"))  # supplier body -> title
        body_html = clean_text(product.get("title", ""))          # supplier title -> body_html

        images = [{"src": img["src"]} for img in product.get("images", [])] if product.get("images") else []

        for supplier_variant in product.get("variants", []):
            sku = supplier_variant.get("sku", "").strip()
            quantity = supplier_variant.get("inventory_quantity", 0)
            price = supplier_variant.get("price", "0.00")
            option1 = supplier_variant.get("option1", "")

            if not sku:
                continue

            if sku in sku_to_variant:
                shopify_variant = sku_to_variant[sku]
                inventory_item_id = shopify_variant.get("inventory_item_id")
                product_id = shopify_variant.get("product_id")

                # Update product info (title/body_html/images/price)
                payload = {
                    "product": {
                        "title": title,
                        "body_html": body_html,
                        "vendor": "",
                        "product_type": product.get("product_type", ""),
                        "tags": product.get("tags", ""),
                        "variants": [
                            {
                                "id": shopify_variant["id"],
                                "price": price,
                                "option1": option1
                            }
                        ],
                        "images": images,
                        "published": True
                    }
                }
                update_url = f"{SHOP_URL}/products/{product_id}.json"
                resp = requests.put(update_url, headers=shopify_headers, json=payload)
                
                # Update inventory
                if inventory_item_id:
                    inv_payload = {
                        "location_id": LOCATION_ID,
                        "inventory_item_id": inventory_item_id,
                        "available": quantity
                    }
                    inv_resp = requests.post(f"{SHOP_URL}/inventory_levels/set.json", headers=shopify_headers, json=inv_payload)
                    writer.writerow({"sku": sku, "status": "Updated", "message": f"Inventory: {quantity}, Product update: {resp.status_code}, Inventory update: {inv_resp.status_code}"})
                else:
                    writer.writerow({"sku": sku, "status": "Skipped", "message": "No inventory_item_id found"})
            else:
                writer.writerow({"sku": sku, "status": "Skipped", "message": "SKU not found in Shopify"})
