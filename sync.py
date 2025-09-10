import requests
import os
import re

# ------------------------
# Configuration
# ------------------------
SUPPLIER_API_URL = "https://the-brave-ones-childrens-fashion.myshopify.com/admin/api/2023-10/products.json"
SUPPLIER_TOKEN = os.getenv("SUPPLIER_TOKEN")

SHOP_URL = "https://cgdboutique.myshopify.com/admin/api/2023-10"
SHOPIFY_TOKEN = os.getenv("SHOPIFY_TOKEN")

LOCATION_ID = 79714615616  # Replace with your Shopify location ID

supplier_headers = {"X-Shopify-Access-Token": SUPPLIER_TOKEN}
shopify_headers = {"X-Shopify-Access-Token": SHOPIFY_TOKEN, "Content-Type": "application/json"}

# ------------------------
# Helper functions
# ------------------------
def clean_text(text):
    """Remove unwanted HTML tags and characters from supplier fields"""
    if not text:
        return ""
    text = re.sub(r"<\/?p>", "", text)
    text = re.sub(r"Â", "", text)
    text = re.sub(r"<\/?span.*?>", "", text)
    text = re.sub(r'data-mce-fragment="1"', "", text)
    return text.strip()

def extract_sku(text):
    """Extract numeric SKU from supplier title (adjust regex if needed)"""
    if not text:
        return None
    match = re.search(r'\b\d+\b', text)
    return match.group(0) if match else None

# ------------------------
# Step 1: Fetch Shopify products
# ------------------------
shopify_resp = requests.get(f"{SHOP_URL}/products.json", headers=shopify_headers)
shopify_products = shopify_resp.json().get("products", [])

# ------------------------
# Step 2: Remove duplicate SKUs
# ------------------------
sku_map = {}
for sp in shopify_products:
    for var in sp.get("variants", []):
        sku = var.get("sku")
        if not sku:
            continue
        if sku not in sku_map:
            sku_map[sku] = {"product_id": sp["id"], "variant_id": var["id"], "inventory_item_id": var["inventory_item_id"]}
        else:
            # Duplicate found — delete the extra product
            duplicate_id = sp["id"]
            del_resp = requests.delete(f"{SHOP_URL}/products/{duplicate_id}.json", headers=shopify_headers)
            print(f"Deleted duplicate SKU {sku}, product ID {duplicate_id}: {del_resp.status_code}")

# ------------------------
# Step 3: Fetch supplier products
# ------------------------
supplier_resp = requests.get(SUPPLIER_API_URL, headers=supplier_headers)
if supplier_resp.status_code != 200:
    print("Supplier API request failed:", supplier_resp.text)
    exit(1)

supplier_products = supplier_resp.json().get("products", [])

# ------------------------
# Step 4: Sync products
# ------------------------
for product in supplier_products:
    supplier_sku = extract_sku(product.get("title"))
    if not supplier_sku:
        continue

    title = clean_text(product.get("body_html", "No Title"))  # swapped
    body_html = clean_text(product.get("title", ""))          # swapped

    images = [{"src": img["src"]} for img in product.get("images", [])] if product.get("images") else []

    supplier_variant = product.get("variants", [{}])[0]
    variant_payload = [{
        "option1": "Default",
        "sku": supplier_sku,
        "price": supplier_variant.get("price", "0.00"),
        "inventory_quantity": supplier_variant.get("inventory_quantity", 0),
        "inventory_management": "shopify"
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
        prod_id = sku_map[supplier_sku]["product_id"]
        var_id = sku_map[supplier_sku]["variant_id"]
        inv_id = sku_map[supplier_sku]["inventory_item_id"]

        resp = requests.put(f"{SHOP_URL}/products/{prod_id}.json", headers=shopify_headers, json=payload)
        print(f"Updated product {supplier_sku}: {resp.status_code}")

        # Update inventory
        inv_payload = {
            "location_id": LOCATION_ID,
            "inventory_item_id": inv_id,
            "available": supplier_variant.get("inventory_quantity", 0)
        }
        inv_resp = requests.post(f"{SHOP_URL}/inventory_levels/set.json", headers=shopify_headers, json=inv_payload)
        print(f"Updated inventory {supplier_sku}: {inv_resp.status_code}")
    else:
        # Create new product
        resp = requests.post(f"{SHOP_URL}/products.json", headers=shopify_headers, json=payload)
        print(f"Created product {supplier_sku}: {resp.status_code}")
        created_product = resp.json().get("product", {})
        if created_product:
            sku_map[supplier_sku] = {
                "product_id": created_product["id"],
                "variant_id": created_product["variants"][0]["id"],
                "inventory_item_id": created_product["variants"][0]["inventory_item_id"]
            }

