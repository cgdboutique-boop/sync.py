import os
import requests

# -----------------------------
# CONFIGURATION
# -----------------------------
# Supplier store (read-only)
SUPPLIER_STORE = "the-brave-ones-childrens-fashion.myshopify.com"
SUPPLIER_TOKEN = os.environ.get("SUPPLIER_TOKEN")  # Supplier API token

# Your store (write access)
YOUR_STORE = os.environ.get("SHOPIFY_STORE")       # Your store domain
YOUR_TOKEN = os.environ.get("SHOPIFY_TOKEN")       # Your store API token

API_VERSION = "2025-07"

# -----------------------------
# HELPER FUNCTIONS
# -----------------------------
def fetch_supplier_products():
    url = f"https://{SUPPLIER_STORE}/admin/api/{API_VERSION}/products.json"
    headers = {"X-Shopify-Access-Token": SUPPLIER_TOKEN}
    response = requests.get(url, headers=headers)
    
    if response.status_code != 200:
        print(f"Failed to fetch supplier products: {response.status_code}")
        print(response.text)
        return []
    
    products = response.json().get("products", [])
    print(f"Fetched {len(products)} products from supplier.")
    return products

def find_product_in_store(sku):
    """Check if a variant with this SKU already exists in your store"""
    url = f"https://{YOUR_STORE}/admin/api/{API_VERSION}/products.json?limit=250"
    headers = {"X-Shopify-Access-Token": YOUR_TOKEN}
    response = requests.get(url, headers=headers)
    
    if response.status_code != 200:
        print(f"Failed to fetch your store products: {response.status_code}")
        return None
    
    products = response.json().get("products", [])
    for product in products:
        for variant in product.get("variants", []):
            if variant.get("sku") == sku:
                return product
    return None

def push_product_to_store(product):
    url = f"https://{YOUR_STORE}/admin/api/{API_VERSION}/products.json"
    headers = {"X-Shopify-Access-Token": YOUR_TOKEN, "Content-Type": "application/json"}
    
    # Check if any variant exists in your store
    existing_product = None
    for variant in product.get("variants", []):
        existing_product = find_product_in_store(variant.get("sku"))
        if existing_product:
            break
    
    product_data = {
        "product": {
            "title": product.get("title", "No Title"),
            "body_html": product.get("body_html", ""),
            "vendor": product.get("vendor", ""),
            "product_type": product.get("product_type", ""),
            "variants": [
                {
                    "id": v.get("id") if existing_product else None,
                    "sku": v.get("sku", ""),
                    "price": v.get("price", "0.00"),
                    "inventory_quantity": v.get("inventory_quantity", 0)
                } for v in product.get("variants", [])
            ],
            "images": [{"src": img.get("src")}]()
