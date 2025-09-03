import os
import requests
import re

# Helper function to clean text
def clean_text(text):
    if not text:
        return ""
    # Remove specific HTML tags
    text = re.sub(r"</?p>", "", text)  # remove <p> and </p>
    text = re.sub(r"</?span.*?>", "", text)  # remove <span ...> and </span>
    # Remove specific unwanted fragment
    text = text.replace('Â', "")
    # Strip extra whitespace
    return text.strip()

# Supplier API
SUPPLIER_API_URL = "https://the-brave-ones-childrens-fashion.myshopify.com/admin/api/2023-10/products.json"
SUPPLIER_TOKEN = os.getenv("SUPPLIER_TOKEN")

supplier_headers = {"X-Shopify-Access-Token": SUPPLIER_TOKEN}
supplier_response = requests.get(SUPPLIER_API_URL, headers=supplier_headers)

if supplier_response.status_code != 200:
    print("Supplier API request failed:", supplier_response.text)
    exit(1)

supplier_products = supplier_response.json().get("products", [])

# Shopify API
SHOP_URL = "https://cgdboutique.myshopify.com/admin/api/2023-10/products.json"
SHOPIFY_TOKEN = os.getenv("SHOPIFY_TOKEN")
shopify_headers = {"X-Shopify-Access-Token": SHOPIFY_TOKEN, "Content-Type": "application/json"}

# Fetch existing Shopify products to check SKUs
shopify_response = requests.get(SHOP_URL, headers=shopify_headers)
if shopify_response.status_code != 200:
    print("Shopify API request failed:", shopify_response.text)
    exit(1)

existing_products = shopify_response.json().get("products", [])
sku_to_product_id = {}
for prod in existing_products:
    for variant in prod.get("variants", []):
        sku_to_product_id[variant.get("sku")] = prod.get("id")

# Loop through supplier products
for product in supplier_products:
    variants = []
    for variant in product.get("variants", []):
        variants.append({
            "option1": variant.get("option1", ""),
            "sku": variant.get("sku", ""),
            "inventory_quantity": variant.get("inventory_quantity", 0),
            "price": variant.get("price", "0.00")
        })

    images = [{"src": img["src"]} for img in product.get("images", [])] if product.get("images") else []

    # Swap title and body_html, clean text, remove vendor
    payload = {
        "product": {
            "title": clean_text(product.get("body_html", "No Title")),  # supplier body -> title
            "body_html": clean_text(product.get("title", "")),          # supplier title -> description
