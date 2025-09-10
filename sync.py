import requests
import os
import re
import time

# ------------------------------
# CONFIGURATION
# ------------------------------
SUPPLIER_API_URL = "https://the-brave-ones-childrens-fashion.myshopify.com/admin/api/2023-10/products.json"
SUPPLIER_TOKEN = os.getenv("SUPPLIER_TOKEN")

SHOP_URL = "https://cgdboutique.myshopify.com/admin/api/2023-10/products.json"
SHOPIFY_TOKEN = os.getenv("SHOPIFY_TOKEN")

# Your Shopify location ID
LOCATION_ID = 79714615616  

# ------------------------------
# HELPER FUNCTIONS
# ------------------------------
def clean_text(text):
    """Remove unwanted HTML tags and characters from supplier fields"""
    if not text:
        return ""
    text = re.sub(r"<\/?p>", "", text)
    text = re.sub(r"Â", "", text)
    text = re.sub(r"<span.*?>", "", text)
    text = re.sub(r"</span>", "", text)
    text = re.sub(r'data-mce-fragment="1"', "", text)
    return text.strip()

def extract_sku_from_text(text):
    """Extract SKU number from supplier body_html in format #12345"""
    match = re.search(r"#(\d+)", text)
    if match:
        return match.group(1)
    return None

# ------------------------------
# FETCH SUPPLIER PRODUCTS
# ------------------------------
supplier_headers = {"X-Shopify-Access-Token": SUPPLIER_TOKEN}
supplier_response = requests.get(SUPPLIER_API_URL, headers=supplier_headers)
if supplier_response.status_code != 200:
    print("Supplier API request failed:", supplier_response.text)
    exit(1)

supplier_products = supplier_response.json().get("products", [])

# ------------------------------
# FETCH SHOPIFY PRODUCTS (for duplicate check)
# ------------------------------
shopify_headers = {"X-Shopify-Access-Token": SHOPIFY_TOKEN, "Content-Type": "application/json"}
shopify_response = requests.get(SHOP_URL, headers=shopify_headers)
shopify_products = shopify_response.json().get("products", [])

# Build a map of existing SKUs to variant IDs
existing_sku_map = {}
for p in shopify_products:
    for v in p.get("variants", []):
        sku = v.get("sku")
        if sku:
            existing_sku_map[sku] = {"variant_id": v["id"], "product_id": p["id"]}

# ------------------------------
# PROCESS SUPPLIER PRODUCTS
# ------------------------------
for product in supplier_products:
    variants_payload = []
    body_html_clean = clean_text(product.get("body_html", ""))
    for variant in product.get("variants", []):
        sku = variant.get("sku")
        # If no SKU, extract from supplier body_html
        if not sku:
            extracted_sku = extract_sku_from_text(body_html_clean)
            sku = extracted_sku if extracted_sku else f"AUTO-{int(time.time())}"  # fallback

        variants_payload.append({
            "option1": variant.get("option1", ""),
            "sku": sku,
            "inventory_quantity": variant.get("inventory_quantity", 0),
            "price": variant.get("price", "0.00"),
            "inventory_management": "shopify",
            "inventory_policy": "deny"
        })

    images_payload = [{"src": img["src"]} for img in product.get("images", [])] if product.get("images") else []

    # Swap title/body_html
    title = clean_text(product.get("body_html", "No Title"))
    body_html = clean_text(product.get("title", ""))

    payload = {
        "product": {
            "title": title,
            "body_html": body_html,
            "vendor": "",  # remove vendor
            "product_type": product.get("product_type", ""),
            "tags": product.get("tags", ""),
            "variants": variants_payload,
            "images": images_payload,
            "published": True
        }
    }

    # ------------------------------
    # CREATE OR UPDATE PRODUCT
    # ------------------------------
    matched = None
    for v in variants_payload:
        if v["sku"] in existing_sku_map:
            matched = existing_sku_map[v["sku"]]
            break

    if matched:
        update_url = f"https://cgdboutique.myshopify.com/admin/api/2023-10/products/{matched['product_id']}.json"
        response = requests.put(update_url, headers=shopify_headers, json=payload)
        print("Updated:", response.status_code, response.json())
    else:
        response = requests.post(SHOP_URL, headers=shopify_headers, json=payload)
        print("Created:", response.status_code, response.json())

    # ------------------------------
    # SYNC INVENTORY
    # ------------------------------
    for v in variants_payload:
        if v["sku"] in existing_sku_map:
            variant_id = existing_sku_map[v["sku"]]["variant_id"]
            variant_info = requests.get(
                f"https://cgdboutique.myshopify.com/admin/api/2023-10/variants/{variant_id}.json",
                headers=shopify_headers
            ).json().get("variant", {})
            inventory_item_id = variant_info.get("inventory_item_id")
            if inventory_item_id is not None:
                inventory_url = f"https://cgdboutique.myshopify.com/admin/api/2023-10/inventory_levels/set.json"
                inventory_payload = {
                    "location_id": LOCATION_ID,
                    "inventory_item_id": inventory_item_id,
                    "available": v.get("inventory_quantity", 0)
                }
                inv_response = requests.post(inventory_url, headers=shopify_headers, json=inventory_payload)
                print(f"Inventory Sync SKU {v['sku']}:", inv_response.status_code, inv_response.json())

    time.sleep(0.2)

print("Sync complete!")
