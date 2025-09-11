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

# Shopify REST API version
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

def push_product_to_store(product):
    url = f"https://{YOUR_STORE}/admin/api/{API_VERSION}/products.json"
    headers = {"X-Shopify-Access-Token": YOUR_TOKEN, "Content-Type": "application/json"}
    
    # Prepare product payload
    product_data = {
        "product": {
            "title": product.get("title", "No Title"),
            "body_html": product.get("body_html", ""),
            "vendor": product.get("vendor", ""),
            "product_type": product.get("product_type", ""),
            "variants": [
                {
                    "sku": v.get("sku", ""),
                    "price": v.get("price", "0.00"),
                    "inventory_quantity": v.get("inventory_quantity", 0)
                } for v in product.get("variants", [])
            ],
            "images": [{"src": img.get("src")} for img in product.get("images", [])]
        }
    }
    
    response = requests.post(url, headers=headers, json=product_data)
    
    if response.status_code in [200, 201]:
        print(f"✅ Successfully created: {product.get('title')}")
    else:
        print(f"❌ Failed to create: {product.get('title')}")
        print(response.status_code, response.text)

# -----------------------------
# MAIN SYNC PROCESS
# -----------------------------
def main():
    supplier_products = fetch_supplier_products()
    
    if not supplier_products:
        print("No products to sync.")
        return
    
    for product in supplier_products:
        push_product_to_store(product)

if __name__ == "__main__":
    main()
