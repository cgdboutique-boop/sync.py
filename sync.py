import os
import requests

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

    # Swap title and body_html, remove vendor
    payload = {
        "product": {
            "title": product.get("body_html", "No Title"),   # supplier body -> title
            "body_html": product.get("title", ""),           # supplier title -> description
            "product_type": product.get("product_type", ""),
            "tags": ",".join(product.get("tags", [])) if isinstance(product.get("tags"), list) else product.get("tags", ""),
            "variants": variants,
            "images": images,
            "published": True
            # vendor removed
        }
    }

    # Check if SKU already exists
    supplier_sku = variants[0].get("sku")
    if supplier_sku in sku_to_product_id:
        product_id = sku_to_product_id[supplier_sku]
        update_url = f"https://cgdboutique.myshopify.com/admin/api/2023-10/products/{product_id}.json"
        response = requests.put(update_url, headers=shopify_headers, json=payload)
        print(f"Updated SKU {supplier_sku}: {response.status_code}")
    else:
        response = requests.post(SHOP_URL, headers=shopify_headers, json=payload)
        print(f"Created SKU {supplier_sku}: {response.status_code}")
