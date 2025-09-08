import requests
import os
import re

# Supplier API
SUPPLIER_API_URL = "https://the-brave-ones-childrens-fashion.myshopify.com/admin/api/2023-10/products.json"
SUPPLIER_TOKEN = os.getenv("SUPPLIER_TOKEN")

supplier_headers = {"X-Shopify-Access-Token": SUPPLIER_TOKEN}
supplier_response = requests.get(SUPPLIER_API_URL, headers=supplier_headers)

if supplier_response.status_code != 200:
    print("Supplier API request failed:", supplier_response.text)
    exit(1)

supplier_products = supplier_response.json().get("products", [])

# Your Shopify store API
SHOP_URL = "https://cgdboutique.myshopify.com/admin/api/2023-10/products.json"
SHOPIFY_TOKEN = os.getenv("SHOPIFY_TOKEN")
shopify_headers = {
    "X-Shopify-Access-Token": SHOPIFY_TOKEN,
    "Content-Type": "application/json"
}

# 🔹 Replace with your Location ID
LOCATION_ID = 79714615616  

def clean_text(text):
    """Remove unwanted HTML tags and characters from supplier fields"""
    if not text:
        return ""
    text = re.sub(r"<\/?p>", "", text)
    text = re.sub(r"Â", "", text)
    text = re.sub(r"<\/?span.*?>", "", text)
    text = re.sub(r"data-mce-fragment=\"1\"", "", text)
    return text.strip()

def get_product_by_sku(sku):
    """Check if a product variant with this SKU already exists in Shopify"""
    url = f"https://cgdboutique.myshopify.com/admin/api/2023-10/variants.json"
    response = requests.get(url, headers=shopify_headers, params={"sku": sku})
    if response.status_code == 200:
        variants = response.json().get("variants", [])
        if variants:
            return variants[0]  # return first match
    return None

def delete_product(product_id):
    """Delete a product from Shopify"""
    url = f"https://cgdboutique.myshopify.com/admin/api/2023-10/products/{product_id}.json"
    response = requests.delete(url, headers=shopify_headers)
    print("Deleted duplicate:", product_id, response.status_code)

for product in supplier_products:
    for variant in product.get("variants", []):
        sku = variant.get("sku")
        if not sku:
            continue  # skip if SKU missing

        existing_variant = get_product_by_sku(sku)

        # Build cleaned data
        variants = [{
            "option1": variant.get("option1", ""),
            "sku": sku,
            "inventory_quantity": variant.get("inventory_quantity", 0),
            "price": variant.get("price", "0.00"),
            "inventory_management": "shopify",
            "inventory_policy": "deny"
        }]

        images = [{"src": img["src"]} for img in product.get("images", [])] if product.get("images") else []

        title = clean_text(product.get("body_html", "No Title"))
        body_html = clean_text(product.get("title", ""))

        payload = {
            "product": {
                "title": title,
                "body_html": body_html,
                "vendor": "",  # remove vendor
                "product_type": product.get("product_type", ""),
                "tags": product.get("tags", ""),
                "variants": variants,
                "images": images,
                "published": True
            }
        }

        if existing_variant:
            # 🔹 Update existing product
            product_id = existing_variant["product_id"]
            update_url = f"https://cgdboutique.myshopify.com/admin/api/2023-10/products/{product_id}.json"
            response = requests.put(update_url, headers=shopify_headers, json=payload)
            print("Updated:", sku, response.status_code)
        else:
            # 🔹 Create new product
            response = requests.post(SHOP_URL, headers=shopify_headers, json=payload)
            print("Created:", sku, response.status_code)

        # 🔹 Sync inventory
        if existing_variant:
            inventory_item_id = existing_variant["inventory_item_id"]
        else:
            created_product = response.json().get("product", {})
            inventory_item_id = created_product.get("variants", [{}])[0].get("inventory_item_id")

        if inventory_item_id:
            inventory_url = "https://cgdboutique.myshopify.com/admin/api/2023-10/inventory_levels/set.json"
            inventory_payload = {
                "location_id": LOCATION_ID,
                "inventory_item_id": inventory_item_id,
                "available": variant.get("inventory_quantity", 0)
            }
            inv_response = requests.post(inventory_url, headers=shopify_headers, json=inventory_payload)
            print("Inventory Sync:", sku, inv_response.status_code)
