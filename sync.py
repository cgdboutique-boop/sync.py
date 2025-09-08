import requests
import os
import re

# -------------------------------
# 🔹 Tokens via GitHub secrets
# -------------------------------
SUPPLIER_TOKEN = os.getenv("SUPPLIER_TOKEN")
SHOPIFY_TOKEN = os.getenv("SHOPIFY_TOKEN")

# Supplier API
SUPPLIER_API_URL = "https://the-brave-ones-childrens-fashion.myshopify.com/admin/api/2023-10/products.json"
supplier_headers = {"X-Shopify-Access-Token": SUPPLIER_TOKEN}

# Shopify API
SHOP_URL = "https://cgdboutique.myshopify.com/admin/api/2023-10/products.json"
shopify_headers = {
    "X-Shopify-Access-Token": SHOPIFY_TOKEN,
    "Content-Type": "application/json"
}

# 🔹 Replace with your Shopify Location ID
LOCATION_ID = 79714615616

# -------------------------------
# Clean text from unwanted HTML
# -------------------------------
def clean_text(text):
    if not text:
        return ""
    text = re.sub(r"<\/?p>", "", text)
    text = re.sub(r"Â", "", text)
    text = re.sub(r"<\/?span.*?>", "", text)
    text = re.sub(r"data-mce-fragment=\"1\"", "", text)
    return text.strip()

# -------------------------------
# Fetch supplier products
# -------------------------------
supplier_response = requests.get(SUPPLIER_API_URL, headers=supplier_headers)
if supplier_response.status_code != 200:
    print("Supplier API request failed:", supplier_response.text)
    exit(1)

supplier_products = supplier_response.json().get("products", [])

# -------------------------------
# Helper: fetch Shopify products by SKU
# -------------------------------
def get_shopify_products_by_sku(sku):
    search_url = f"https://cgdboutique.myshopify.com/admin/api/2023-10/products.json?sku={sku}"
    res = requests.get(search_url, headers=shopify_headers)
    return res.json().get("products", [])

# -------------------------------
# Sync supplier products
# -------------------------------
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

    # Swap title and body_html
    title = clean_text(product.get("body_html", "No Title"))
    body_html = clean_text(product.get("title", ""))

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

    # -------------------------------
    # Check for duplicates by SKU
    # -------------------------------
    for variant in product.get("variants", []):
        sku = variant.get("sku")
        if not sku:
            continue
        existing_products = get_shopify_products_by_sku(sku)

        # If more than 1 product exists, delete duplicates (keep the first)
        if len(existing_products) > 1:
            for dup_product in existing_products[1:]:
                delete_url = f"https://cgdboutique.myshopify.com/admin/api/2023-10/products/{dup_product['id']}.json"
                del_res = requests.delete(delete_url, headers=shopify_headers)
                print(f"Deleted duplicate product ID {dup_product['id']} for SKU {sku}: {del_res.status_code}")

    # -------------------------------
    # Create or update product
    # -------------------------------
    existing_product = get_shopify_products_by_sku(variants[0]["sku"]) if variants else []
    if existing_product:
        product_id = existing_product[0]["id"]
        update_url = f"https://cgdboutique.myshopify.com/admin/api/2023-10/products/{product_id}.json"
        response = requests.put(update_url, headers=shopify_headers, json=payload)
        print("Updated:", response.status_code)
        shop_product = response.json().get("product", {})
    else:
        response = requests.post(SHOP_URL, headers=shopify_headers, json=payload)
        print("Created:", response.status_code)
        shop_product = response.json().get("product", {})

    # -------------------------------
    # Sync inventory
    # -------------------------------
    for shop_variant, supplier_variant in zip(shop_product.get("variants", []), product.get("variants", [])):
        inventory_url = "https://cgdboutique.myshopify.com/admin/api/2023-10/inventory_levels/set.json"
        inv_payload = {
            "location_id": LOCATION_ID,
            "inventory_item_id": shop_variant.get("inventory_item_id"),
            "available": supplier_variant.get("inventory_quantity", 0)
        }
        inv_res = requests.post(inventory_url, headers=shopify_headers, json=inv_payload)
        print(f"Inventory synced for SKU {shop_variant.get('sku')}: {inv_res.status_code}")
