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

LOCATION_ID = 79714615616  # Your Shopify location ID

supplier_headers = {"X-Shopify-Access-Token": SUPPLIER_TOKEN}
shopify_headers = {"X-Shopify-Access-Token": SHOPIFY_TOKEN, "Content-Type": "application/json"}

# -----------------------------
# Helper functions
# -----------------------------
def clean_text(text):
    """Remove unwanted HTML tags/characters."""
    if not text:
        return ""
    text = re.sub(r"<\/?p>", "", text)
    text = re.sub(r"Â", "", text)
    text = re.sub(r"<\/?span.*?>", "", text)
    text = re.sub(r'data-mce-fragment="1"', "", text)
    return text.strip()

def extract_sku(text):
    """Extract SKU from supplier title."""
    if not text:
        return None
    match = re.search(r'\b\d+\b', text)
    return match.group(0) if match else None

# -----------------------------
# Fetch supplier products
# -----------------------------
supplier_resp = requests.get(SUPPLIER_API_URL, headers=supplier_headers)
if supplier_resp.status_code != 200:
    print("Supplier API request failed:", supplier_resp.text)
    exit(1)

supplier_products = supplier_resp.json().get("products", [])

# -----------------------------
# Fetch Shopify products
# -----------------------------
shopify_resp = requests.get(f"{SHOP_URL}/products.json", headers=shopify_headers)
if shopify_resp.status_code != 200:
    print("Shopify API request failed:", shopify_resp.text)
    exit(1)

shopify_products = shopify_resp.json().get("products", [])

# Build a mapping: SKU → existing product
shopify_sku_map = {}
for sp in shopify_products:
    sku_in_body = extract_sku(sp.get("body_html", ""))
    if sku_in_body:
        shopify_sku_map[sku_in_body] = sp

# -----------------------------
# Sync products
# -----------------------------
for product in supplier_products:
    supplier_sku = extract_sku(product.get("title", ""))
    if not supplier_sku:
        continue

    supplier_qty = product["variants"][0].get("inventory_quantity", 0)
    supplier_price = product["variants"][0].get("price", "0.00")

    # Swap title and body_html
    title = clean_text(product.get("body_html", "No Title"))
    body_html = clean_text(product.get("title", ""))

    images = [{"src": img["src"]} for img in product.get("images", [])] if product.get("images") else []

    variant_payload = [{
        "option1": "Default",
        "sku": supplier_sku,
        "price": supplier_price,
        "inventory_quantity": supplier_qty,
        "inventory_management": "shopify"
    }]

    payload = {
        "product": {
            "title": title,
            "body_html": body_html,
            "vendor": "",  # remove vendor
            "product_type": product.get("product_type", ""),
            "tags": product.get("tags", ""),
            "variants": variant_payload,
            "images": images,
            "published": True
        }
    }

    if supplier_sku in shopify_sku_map:
        # Update existing product
        existing_product = shopify_sku_map[supplier_sku]
        product_id = existing_product["id"]
        update_url = f"{SHOP_URL}/products/{product_id}.json"
        resp = requests.put(update_url, headers=shopify_headers, json=payload)
        print(f"Updated product {supplier_sku}: {resp.status_code}")

        # Update inventory for first variant
        variant_id = existing_product["variants"][0]["id"]
        inventory_item_id = existing_product["variants"][0]["inventory_item_id"]
        inventory_payload = {
            "location_id": LOCATION_ID,
            "inventory_item_id": inventory_item_id,
            "available": supplier_qty
        }
        inv_resp = requests.post(f"{SHOP_URL}/inventory_levels/set.json", headers=shopify_headers, json=inventory_payload)
        print(f"Updated inventory {supplier_sku}: {inv_resp.status_code}")

    else:
        # Create new product
        resp = requests.post(f"{SHOP_URL}/products.json", headers=shopify_headers, json=payload)
        print(f"Created product {supplier_sku}: {resp.status_code}")
