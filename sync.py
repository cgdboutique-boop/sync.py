import requests
import os
import re

# ------------------------------
# CONFIGURATION
# ------------------------------
SUPPLIER_API_URL = "https://the-brave-ones-childrens-fashion.myshopify.com/admin/api/2023-10/products.json"
SUPPLIER_TOKEN = os.getenv("SUPPLIER_TOKEN")

SHOP_URL = "https://cgdboutique.myshopify.com/admin/api/2023-10/products.json"
SHOPIFY_TOKEN = os.getenv("SHOPIFY_TOKEN")

# Location ID for inventory syncing
LOCATION_ID = 79714615616  

headers_supplier = {"X-Shopify-Access-Token": SUPPLIER_TOKEN}
headers_shop = {"X-Shopify-Access-Token": SHOPIFY_TOKEN, "Content-Type": "application/json"}

# ------------------------------
# HELPER FUNCTIONS
# ------------------------------
def clean_text(text):
    """Remove unwanted HTML tags and characters from supplier fields"""
    if not text:
        return ""
    text = re.sub(r"<\/?p>", "", text)
    text = re.sub(r"Â", "", text)
    text = re.sub(r"<\/?span.*?>", "", text)
    text = re.sub(r"data-mce-fragment=\"1\"", "", text)
    return text.strip()

def extract_sku_from_body(body):
    """Fallback SKU from #number in body_html if SKU missing"""
    match = re.search(r"#(\d+)", body)
    return match.group(1) if match else None

# ------------------------------
# FETCH SUPPLIER PRODUCTS
# ------------------------------
supplier_resp = requests.get(SUPPLIER_API_URL, headers=headers_supplier)
if supplier_resp.status_code != 200:
    print("Supplier API request failed:", supplier_resp.text)
    exit(1)

supplier_products = supplier_resp.json().get("products", [])

# ------------------------------
# SYNC PRODUCTS
# ------------------------------
for product in supplier_products:
    variants = []
    for variant in product.get("variants", []):
        sku = variant.get("sku") or extract_sku_from_body(product.get("body_html", ""))
        variants.append({
            "option1": variant.get("option1", ""),
            "sku": sku,
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
            "vendor": product.get("vendor", ""),  # Keep vendor
            "product_type": product.get("product_type", ""),
            "tags": product.get("tags", ""),
            "variants": variants,
            "images": images,
            "published": True
        }
    }

    # Check if product exists by SKU
    existing_products = []
    for v in variants:
        sku_query = v.get("sku")
        if sku_query:
            resp = requests.get(SHOP_URL, headers=headers_shop, params={"sku": sku_query})
            existing_products += resp.json().get("products", [])

    if existing_products:
        # Update the first matched product
        product_id = existing_products[0]["id"]
        update_url = f"https://cgdboutique.myshopify.com/admin/api/2023-10/products/{product_id}.json"
        resp = requests.put(update_url, headers=headers_shop, json=payload)
        print("Updated:", resp.status_code, resp.json())
    else:
        # Create new product
        resp = requests.post(SHOP_URL, headers=headers_shop, json=payload)
        print("Created:", resp.status_code, resp.json())

    # Sync inventory for each variant
    for variant in variants:
        if "sku" in variant:
            # Get variant ID from created/updated product
            if existing_products:
                variant_id = existing_products[0]["variants"][0]["id"]
            else:
                created_product = resp.json().get("product", {})
                variant_id = created_product.get("variants", [{}])[0].get("id")

            if variant_id:
                inventory_url = f"https://cgdboutique.myshopify.com/admin/api/2023-10/inventory_levels/set.json"
                inventory_payload = {
                    "location_id": LOCATION_ID,
                    "inventory_item_id": variant_id,
                    "available": variant.get("inventory_quantity", 0)
                }
                inv_resp = requests.post(inventory_url, headers=headers_shop, json=inventory_payload)
                print("Inventory Sync SKU {}:".format(variant["sku"]), inv_resp.status_code)
