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

# 🔹 Replace this with your Location ID (from Shopify > Settings > Locations)
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

def find_product_by_sku(sku):
    """Search Shopify for a product by SKU"""
    search_url = f"https://cgdboutique.myshopify.com/admin/api/2023-10/products.json"
    response = requests.get(search_url, headers=shopify_headers, params={"sku": sku})
    if response.status_code == 200:
        products = response.json().get("products", [])
        if products:
            return products[0]  # Return the first matching product
    return None

for product in supplier_products:
    if not product.get("variants"):
        continue  # Skip products without variants

    # Take SKU from the first variant
    sku = product["variants"][0].get("sku", "")
    if not sku:
        continue  # Skip if no SKU

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

    # 🔹 Swap supplier title/body, remove vendor
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

    # 🔹 Check by SKU instead of title
    existing_product = find_product_by_sku(sku)

    if existing_product:
        product_id = existing_product["id"]
        update_url = f"https://cgdboutique.myshopify.com/admin/api/2023-10/products/{product_id}.json"
        response = requests.put(update_url, headers=shopify_headers, json=payload)
        print("Updated:", response.status_code, response.json())
    else:
        response = requests.post(SHOP_URL, headers=shopify_headers, json=payload)
        print("Created:", response.status_code, response.json())

    # 🔹 Sync inventory for each variant
    for variant in product.get("variants", []):
        if "sku" in variant and variant.get("inventory_quantity") is not None:
            # Get variant ID from created/updated product
            if existing_product:
                variant_id = existing_product["variants"][0]["id"]
            else:
                created_product = response.json().get("product", {})
                variant_id = created_product.get("variants", [{}])[0].get("id")

            if variant_id:
                inventory_url = f"https://cgdboutique.myshopify.com/admin/api/2023-10/inventory_levels/set.json"
                inventory_payload = {
                    "location_id": LOCATION_ID,
                    "inventory_item_id": variant.get("inventory_item_id"),
                    "available": variant.get("inventory_quantity", 0)
                }
                inv_response = requests.post(inventory_url, headers=shopify_headers, json=inventory_payload)
                print("Inventory Sync:", inv_response.status_code, inv_response.json())

