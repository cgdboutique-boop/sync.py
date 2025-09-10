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

# 🔹 Your Shopify Location ID (Settings > Locations)
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

# ---------------- Process Supplier Products ----------------
for product in supplier_products:
    variants = []
    for variant in product.get("variants", []):
        variants.append({
            "option1": variant.get("option1", ""),
            "sku": variant.get("sku", ""),
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
            "vendor": "",  # no supplier vendor
            "product_type": product.get("product_type", ""),
            "tags": product.get("tags", ""),
            "variants": variants,
            "images": images,
            "published": True
        }
    }

    # ---------------- Step 1: Check by SKU (avoid duplicates) ----------------
    created_or_updated_product = None
    for sup_variant in product.get("variants", []):
        sku = sup_variant.get("sku")
        if not sku:
            continue

        # Search Shopify by SKU
        search_url = f"https://cgdboutique.myshopify.com/admin/api/2023-10/products.json"
        search_response = requests.get(search_url, headers=shopify_headers, params={"sku": sku})

        if search_response.status_code == 200 and search_response.json().get("products"):
            created_or_updated_product = search_response.json()["products"][0]
            product_id = created_or_updated_product["id"]

            # Update existing product
            update_url = f"https://cgdboutique.myshopify.com/admin/api/2023-10/products/{product_id}.json"
            response = requests.put(update_url, headers=shopify_headers, json=payload)
            print(f"Updated product with SKU {sku}: {response.status_code}")
        else:
            # Create new product
            response = requests.post(SHOP_URL, headers=shopify_headers, json=payload)
            created_or_updated_product = response.json().get("product", {})
            print(f"Created new product with SKU {sku}: {response.status_code}")
        break  # only need to check the first variant’s SKU to decide

    # ---------------- Step 2: Sync Inventory by SKU ----------------
    if created_or_updated_product:
        shopify_variants = created_or_updated_product.get("variants", [])
        for sup_variant in product.get("variants", []):
            sku = sup_variant.get("sku")
            qty = sup_variant.get("inventory_quantity", 0)

            # Match variant by SKU in Shopify
            matching_variant = next((v for v in shopify_variants if v.get("sku") == sku), None)
            if matching_variant:
                inventory_item_id = matching_variant.get("inventory_item_id")

                inventory_url = "https://cgdboutique.myshopify.com/admin/api/2023-10/inventory_levels/set.json"
                inventory_payload = {
                    "location_id": LOCATION_ID,
                    "inventory_item_id": inventory_item_id,
                    "available": qty
                }
                inv_response = requests.post(inventory_url, headers=shopify_headers, json=inventory_payload)
                print(f"Inventory Sync for SKU {sku}: {inv_response.status_code}")
