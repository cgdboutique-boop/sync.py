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

# Replace with your Shopify Location ID for inventory updates
LOCATION_ID = 79714615616  

supplier_headers = {"X-Shopify-Access-Token": SUPPLIER_TOKEN}
shopify_headers = {"X-Shopify-Access-Token": SHOPIFY_TOKEN, "Content-Type": "application/json"}

# -----------------------------
# Helper Functions
# -----------------------------
def clean_text(text):
    """Remove unwanted HTML tags and characters"""
    if not text:
        return ""
    text = re.sub(r"<\/?p>", "", text)
    text = re.sub(r"Â", "", text)
    text = re.sub(r"<\/?span.*?>", "", text)
    text = re.sub(r'data-mce-fragment="1"', "", text)
    return text.strip()

def extract_sku_from_body(body_html):
    """Extract SKU from body_html (assuming SKU is numeric)"""
    if not body_html:
        return None
    match = re.search(r'\b\d+\b', body_html)
    return match.group(0) if match else None

# -----------------------------
# Fetch supplier products
# -----------------------------
supplier_response = requests.get(SUPPLIER_API_URL, headers=supplier_headers)
if supplier_response.status_code != 200:
    print("Supplier API request failed:", supplier_response.text)
    exit(1)

supplier_products = supplier_response.json().get("products", [])

# -----------------------------
# Fetch Shopify products
# -----------------------------
shopify_products_response = requests.get(f"{SHOP_URL}/products.json", headers=shopify_headers)
if shopify_products_response.status_code != 200:
    print("Shopify API request failed:", shopify_products_response.text)
    exit(1)
shopify_products = shopify_products_response.json().get("products", [])

# -----------------------------
# Sync logic
# -----------------------------
for product in supplier_products:
    supplier_sku = product.get("title", "").strip()  # SKU is in supplier title
    supplier_qty = product["variants"][0].get("inventory_quantity", 0)
    supplier_price = product["variants"][0].get("price", "0.00")

    # Search Shopify for matching SKU in body_html
    matched_product = None
    matched_variant = None
    for sp in shopify_products:
        sku_in_body = extract_sku_from_body(sp.get("body_html", ""))
        if sku_in_body == supplier_sku:
            matched_product = sp
            matched_variant = sp["variants"][0]
            break

    if matched_product:
        # Update existing product
        variant_id = matched_variant["id"]
        inventory_item_id = matched_variant["inventory_item_id"]

        # Update variant price & SKU
        update_url = f"{SHOP_URL}/variants/{variant_id}.json"
        update_payload = {
            "variant": {
                "id": variant_id,
                "price": supplier_price,
                "sku": supplier_sku
            }
        }
        response = requests.put(update_url, headers=shopify_headers, json=update_payload)
        print(f"Updated price/SKU for {supplier_sku}: {response.status_code}")

        # Update inventory
        inventory_url = f"{SHOP_URL}/inventory_levels/set.json"
        inventory_payload = {
            "location_id": LOCATION_ID,
            "inventory_item_id": inventory_item_id,
            "available": supplier_qty
        }
        inv_response = requests.post(inventory_url, headers=shopify_headers, json=inventory_payload)
        print(f"Updated inventory for {supplier_sku}: {inv_response.status_code}")

    else:
        # Create new product
        title = clean_text(product.get("body_html", "No Title"))
        body_html = clean_text(product.get("title", ""))
        variants = [{
            "option1": "Default",
            "sku": supplier_sku,
            "price": supplier_price,
            "inventory_quantity": supplier_qty,
            "inventory_management": "shopify"
        }]
        images = [{"src": img["src"]} for img in product.get("images", [])] if product.get("images") else []

        payload = {
            "product": {
                "title": title,
                "body_html": body_html,
                "vendor": "",
                "product_type": product.get("product_type", ""),
                "tags": product.get("tags", ""),
                "variants": variants,
                "images": images,
                "published": True
            }
        }
        response = requests.post(f"{SHOP_URL}/products.json", headers=shopify_headers, json=payload)
        print(f"Created new product {supplier_sku}: {response.status_code}")
