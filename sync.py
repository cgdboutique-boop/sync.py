import requests
import os

# Supplier API
supplier_api_url = "https://the-brave-ones-childrens-fashion.myshopify.com/admin/api/2023-10/products.json"
supplier_headers = {
    "X-Shopify-Access-Token": os.getenv("SUPPLIER_TOKEN")
}
supplier_response = requests.get(supplier_api_url, headers=supplier_headers)

if supplier_response.status_code != 200:
    print("❌ Supplier API request failed:", supplier_response.text)
    exit(1)

supplier_data = supplier_response.json()

# Shopify API (your store)
shop_url = "https://cgdboutique.myshopify.com/admin/api/2023-10/products.json"
shop_headers = {
    "X-Shopify-Access-Token": os.getenv("SHOPIFY_TOKEN"),
    "Content-Type": "application/json"
}

# Loop through supplier products and push to your Shopify
for product in supplier_data.get("products", []):
    payload = {
        "product": {
            "title": product.get("title", ""),
            "body_html": product.get("body_html", ""),
            "variants": [
                {
                    "price": product["variants"][0].get("price", "0.00"),
                    "sku": product["variants"][0].get("sku", ""),
                    "inventory_quantity": product["variants"][0].get("inventory_quantity", 0)
                }
            ]
        }
    }

    response = requests.post(shop_url, headers=shop_headers, json=payload)
    print(response.status_code, response.json())
