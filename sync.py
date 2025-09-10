import requests
import os
import re

# Supplier API
SUPPLIER_API_URL = "https://the-brave-ones-childrens-fashion.myshopify.com/admin/api/2023-10/products.json"
SUPPLIER_TOKEN = os.getenv("SUPPLIER_TOKEN")

supplier_headers = {"X-Shopify-Access-Token": SUPPLIER_TOKEN}
supplier_response = requests.get(SUPPLIER_API_URL, headers=supplier_headers)

if supplier_response.status_code != 200:
    print("❌ Supplier API request failed:", supplier_response.text)
    exit(1)

supplier_products = supplier_response.json().get("products", [])

# Your Shopify store API
SHOP_URL = "https://cgdboutique.myshopify.com/admin/api/2023-10"
SHOPIFY_TOKEN = os.getenv("SHOPIFY_TOKEN")
shopify_headers = {
    "X-Shopify-Access-Token": SHOPIFY_TOKEN,
    "Content-Type": "application/json"
}

# 🔹 Replace this with your Location ID
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
    url = f"{SHOP_URL}/products.json"
    response = requests.get(url, headers=shopify_headers, params={"sku": sku, "limit": 1})
    if response.status_code == 200:
        products = response.json().get("products", [])
        if products:
            return products[0]
    return None

for product in supplier_products:
    for variant in product.get("variants", []):
        supplier_sku = variant.get("sku", "")
        if not supplier_sku:
            continue  

        supplier_qty = variant.get("inventory_quantity", 0)
        supplier_price = variant.get("price", "0.00")

        print(f"🔍 Checking supplier SKU: {supplier_sku}, Qty: {supplier_qty}, Price: {supplier_price}")

        # Check Shopify for matching SKU
        shopify_product = find_product_by_sku(supplier_sku)

        if shopify_product:
            print(f"✅ Found in Shopify: {supplier_sku} -> Updating")

            shopify_variant = shopify_product["variants"][0]  
            variant_id = shopify_variant["id"]
            inventory_item_id = shopify_variant["inventory_item_id"]

            # Update variant details
            update_url = f"{SHOP_URL}/variants/{variant_id}.json"
            update_payload = {
                "variant": {
                    "id": variant_id,
                    "price": supplier_price,
                    "sku": supplier_sku
                }
            }
            response = requests.put(update_url, headers=shopify_headers, json=update_payload)
            print("🔄 Variant update response:", response.status_code, response.json())

            # Update inventory
            inventory_url = f"{SHOP_URL}/inventory_levels/set.json"
            inventory_payload = {
                "location_id": LOCATION_ID,
                "inventory_item_id": inventory_item_id,
                "available": supplier_qty
            }
            inv_response = requests.post(inventory_url, headers=shopify_headers, json=inventory_payload)
            print("📦 Inventory update response:", inv_response.status_code, inv_response.json())

        else:
            print(f"⚠️ SKU {supplier_sku} not found in Shopify -> Creating new product")

            # Clean fields
            title = clean_text(product.get("body_html", "No Title"))
            body_html = clean_text(product.get("title", ""))

            payload = {
                "product": {
                    "title": title,
                    "body_html": body_html,
                    "vendor": "",
                    "product_type": product.get("product_type", ""),
                    "tags": product.get("tags", ""),
                    "variants": [{
                        "option1": variant.get("option1", ""),
                        "sku": supplier_sku,
                        "inventory_quantity": supplier_qty,
                        "price": supplier_price,
                        "inventory_management": "shopify"
                    }],
                    "images": [{"src": img["src"]} for img in product.get("images", [])],
                    "published": True
                }
            }

            response = requests.post(f"{SHOP_URL}/products.json", headers=shopify_headers, json=payload)
            print("🆕 Product create response:", response.status_code, response.json())
