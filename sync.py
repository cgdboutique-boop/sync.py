import requests

# Supplier API
supplier_api_url = "https://supplier.com/api/products"
supplier_headers = {"Authorization": "Bearer YOUR_SUPPLIER_TOKEN"}
supplier_data = requests.get(supplier_api_url, headers=supplier_headers).json()

# Shopify API
shop_url = "https://YOURSHOPNAME.myshopify.com/admin/api/2023-10/products.json"
shop_headers = {
    "X-Shopify-Access-Token": "YOUR_SHOPIFY_ADMIN_API_TOKEN",
    "Content-Type": "application/json"
}

# Loop through supplier products and create/update on Shopify
for product in supplier_data["products"]:
    payload = {
        "product": {
            "title": product["name"],
            "body_html": product["description"],
            "variants": [
                {
                    "price": product["price"],
                    "sku": product["sku"],
                    "inventory_quantity": product["stock"]
                }
            ]
        }
    }
    response = requests.post(shop_url, headers=shop_headers, json=payload)
    print(response.json())
