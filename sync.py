import requests
import os

# 🔹 Supplier API
SUPPLIER_API_URL = "https://the-brave-ones-childrens-fashion.myshopify.com/admin/api/2023-10/products.json"
SUPPLIER_TOKEN = os.getenv("SUPPLIER_TOKEN")

# 🔹 Your Shopify store API
SHOPIFY_API_URL = "https://cgdboutique.myshopify.com/admin/api/2023-10"
SHOPIFY_TOKEN = os.getenv("SHOPIFY_TOKEN")

supplier_headers = {"X-Shopify-Access-Token": SUPPLIER_TOKEN}
shopify_headers = {"X-Shopify-Access-Token": SHOPIFY_TOKEN, "Content-Type": "application/json"}

# 🔹 Fetch supplier products
supplier_response = requests.get(SUPPLIER_API_URL, headers=supplier_headers)
if supplier_response.status_code != 200:
    print("❌ Supplier API request failed:", supplier_response.text)
    exit(1)

supplier_products = supplier_response.json().get("products", [])

# 🔹 Loop through supplier products
for product in supplier_products:
    for variant in product.get("variants", []):
        sku = variant.get("sku")
        if not sku:
            continue  # skip if no SKU

        # Check if Shopify product exists with this SKU
        search_url = f"{SHOPIFY_API_URL}/products.json?sku={sku}"
        search_response = requests.get(search_url, headers=shopify_headers)

        if search_response.status_code != 200:
            print(f"❌ Failed to search for SKU {sku}:", search_response.text)
            continue

        shopify_products = search_response.json().get("products", [])
        if not shopify_products:
            print(f"⚠️ No match found in Shopify for SKU {sku}, skipping.")
            continue

        shopify_product = shopify_products[0]  # Take first match
        product_id = shopify_product["id"]

        # Update product payload
        payload = {
            "product": {
                "id": product_id,
                "title": product.get("title", shopify_product["title"]),
                "body_html": product.get("body_html", shopify_product["body_html"]),
                "variants": [
                    {
                        "id": shopify_product["variants"][0]["id"],
                        "price": variant.get("price", shopify_product["variants"][0]["price"]),
                        "inventory_quantity": variant.get("inventory_quantity", 0)
                    }
                ]
            }
        }

        update_url = f"{SHOPIFY_API_URL}/products/{product_id}.json"
        update_response = requests.put(update_url, headers=shopify_headers, json=payload)

        if update_response.status_code == 200:
            print(f"✅ Updated SKU {sku}")
        else:
            print(f"❌ Failed to update SKU {sku}:", update_response.text)
