import os
import requests

# Supplier API
SUPPLIER_API_URL = "https://the-brave-ones-childrens-fashion.myshopify.com/admin/api/2023-10/products.json"
SUPPLIER_TOKEN = os.getenv("SUPPLIER_TOKEN")
supplier_headers = {"X-Shopify-Access-Token": SUPPLIER_TOKEN}
supplier_response = requests.get(SUPPLIER_API_URL, headers=supplier_headers)
supplier_products = supplier_response.json().get("products", [])

# Your Shopify API
SHOP_URL = "https://cgdboutique.myshopify.com/admin/api/2023-10"
SHOPIFY_TOKEN = os.getenv("SHOPIFY_TOKEN")
shopify_headers = {"X-Shopify-Access-Token": SHOPIFY_TOKEN, "Content-Type": "application/json"}

def find_variant_by_sku(sku):
    url = f"{SHOP_URL}/variants.json?sku={sku}"
    r = requests.get(url, headers=shopify_headers)
    if r.status_code == 200:
        variants = r.json().get("variants", [])
        return variants[0] if variants else None
    return None

for product in supplier_products:
    for variant in product.get("variants", []):
        sku = variant.get("sku")
        if not sku:
            continue  # skip if no SKU

        existing_variant = find_variant_by_sku(sku)

        if existing_variant:
            # Update price
            update_variant_url = f"{SHOP_URL}/variants/{existing_variant['id']}.json"
            payload = {"variant": {"id": existing_variant["id"], "price": variant.get("price", "0.00")}}
            requests.put(update_variant_url, headers=shopify_headers, json=payload)

            # Update inventory
            inventory_item_id = existing_variant["inventory_item_id"]
            location_url = f"{SHOP_URL}/locations.json"
            location_id = requests.get(location_url, headers=shopify_headers).json()["locations"][0]["id"]

            inventory_url = f"{SHOP_URL}/inventory_levels/set.json"
            inventory_payload = {
                "location_id": location_id,
                "inventory_item_id": inventory_item_id,
                "available": variant.get("inventory_quantity", 0)
            }
            requests.post(inventory_url, headers=shopify_headers, json=inventory_payload)

        else:
            # Product doesn’t exist → create new one
            payload = {
                "product": {
                    "title": product.get("title", "No Title"),
                    "body_html": product.get("body_html", ""),
                    "vendor": product.get("vendor", ""),
                    "product_type": product.get("product_type", ""),
                    "tags": ",".join(product.get("tags", [])) if isinstance(product.get("tags"), list) else product.get("tags", ""),
                    "variants": [{
                        "option1": variant.get("option1", ""),
                        "sku": sku,
                        "price": variant.get("price", "0.00")
                    }],
                    "images": [{"src": img["src"]} for img in product.get("images", [])] if product.get("images") else [],
                    "published": True
                }
            }
            requests.post(f"{SHOP_URL}/products.json", headers=shopify_headers, json=payload)
