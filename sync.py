import requests
import os
import re

# -------------------------
# CONFIGURATION
# -------------------------

SUPPLIER_API_URL = "https://the-brave-ones-childrens-fashion.myshopify.com/admin/api/2023-10/products.json"
SUPPLIER_TOKEN = os.getenv("SUPPLIER_TOKEN")  # GitHub Secret

SHOP_URL = "https://cgdboutique.myshopify.com/admin/api/2023-10/products.json"
SHOPIFY_TOKEN = os.getenv("SHOPIFY_TOKEN")    # GitHub Secret

# Your Shopify location ID for inventory updates
LOCATION_ID = 79714615616  # Replace with your actual location ID

# -------------------------
# HELPER FUNCTIONS
# -------------------------

def clean_text(text):
    """Remove unwanted HTML tags and characters"""
    if not text:
        return ""
    text = re.sub(r"</?p>", "", text)
    text = re.sub(r"Â", "", text)
    text = re.sub(r"<span.*?>", "", text)
    text = re.sub(r"data-mce-fragment=\"1\"", "", text)
    return text.strip()

def get_shopify_products():
    """Fetch all products from Shopify"""
    response = requests.get(SHOP_URL, headers={"X-Shopify-Access-Token": SHOPIFY_TOKEN})
    if response.status_code != 200:
        print("Error fetching Shopify products:", response.text)
        return []
    return response.json().get("products", [])

def find_product_by_sku(products, sku):
    """Return the first product that matches the SKU"""
    for product in products:
        for variant in product.get("variants", []):
            if variant.get("sku") == sku:
                return product
    return None

# -------------------------
# MAIN SYNC LOGIC
# -------------------------

# Fetch supplier products
supplier_headers = {"X-Shopify-Access-Token": SUPPLIER_TOKEN}
supplier_resp = requests.get(SUPPLIER_API_URL, headers=supplier_headers)
if supplier_resp.status_code != 200:
    print("Supplier API request failed:", supplier_resp.text)
    exit(1)
supplier_products = supplier_resp.json().get("products", [])

# Fetch current Shopify products
shopify_products = get_shopify_products()

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

    # Swap title/body_html
    title = clean_text(product.get("body_html", "No Title"))
    body_html = clean_text(product.get("title", ""))

    payload = {
        "product": {
            "title": title,
            "body_html": body_html,
            "vendor": "",  # Remove vendor
            "product_type": product.get("product_type", ""),
            "tags": product.get("tags", ""),
            "variants": variants,
            "images": images,
            "published": True
        }
    }

    # Check if product exists (by SKU)
    existing_product = None
    for variant in product.get("variants", []):
        sku = variant.get("sku")
        existing_product = find_product_by_sku(shopify_products, sku)
        if existing_product:
            break

    if existing_product:
        # Update existing product
        product_id = existing_product["id"]
        update_url = f"https://cgdboutique.myshopify.com/admin/api/2023-10/products/{product_id}.json"
        resp = requests.put(update_url, headers={"X-Shopify-Access-Token": SHOPIFY_TOKEN, "Content-Type": "application/json"}, json=payload)
        print(f"Updated: {title} -> Status {resp.status_code}")
    else:
        # Create new product
        resp = requests.post(SHOP_URL, headers={"X-Shopify-Access-Token": SHOPIFY_TOKEN, "Content-Type": "application/json"}, json=payload)
        print(f"Created: {title} -> Status {resp.status_code}")

    # Sync inventory
    for variant in product.get("variants", []):
        sku = variant.get("sku")
        inventory_qty = variant.get("inventory_quantity", 0)
        existing_variant = None
        if existing_product:
            for v in existing_product.get("variants", []):
                if v.get("sku") == sku:
                    existing_variant = v
                    break
        else:
            created_variant = resp.json().get("product", {}).get("variants", [{}])[0]
            existing_variant = created_variant

        if existing_variant:
            inventory_payload = {
                "location_id": LOCATION_ID,
                "inventory_item_id": existing_variant.get("inventory_item_id"),
                "available": inventory_qty
            }
            inv_url = "https://cgdboutique.myshopify.com/admin/api/2023-10/inventory_levels/set.json"
            inv_resp = requests.post(inv_url, headers={"X-Shopify-Access-Token": SHOPIFY_TOKEN, "Content-Type": "application/json"}, json=inventory_payload)
            print(f"Inventory Sync SKU {sku}: Status {inv_resp.status_code}")
