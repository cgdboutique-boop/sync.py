import requests
import os
import re

# Supplier API
SUPPLIER_API_URL = "https://the-brave-ones-childrens-fashion.myshopify.com/admin/api/2023-10/products.json"
SUPPLIER_TOKEN = os.getenv("SUPPLIER_TOKEN")

# Your Shopify store API
SHOP_URL = "https://cgdboutique.myshopify.com/admin/api/2023-10"
SHOPIFY_TOKEN = os.getenv("SHOPIFY_TOKEN")

supplier_headers = {"X-Shopify-Access-Token": SUPPLIER_TOKEN}
shopify_headers = {"X-Shopify-Access-Token": SHOPIFY_TOKEN, "Content-Type": "application/json"}


def clean_text(text):
    """Remove unwanted tags/characters from titles and descriptions."""
    if not text:
        return ""
    cleaned = re.sub(r"<\/?p>|Â|<\/?span.*?>", "", text)
    return cleaned.strip()


def get_existing_products():
    """Fetch all existing products with SKUs mapped to product + variant IDs."""
    sku_map = {}
    url = f"{SHOP_URL}/products.json?limit=250"
    while url:
        resp = requests.get(url, headers=shopify_headers)
        if resp.status_code != 200:
            break
        data = resp.json()
        products = data.get("products", [])
        for product in products:
            for variant in product.get("variants", []):
                sku = variant.get("sku")
                if sku:
                    sku_map[sku] = {
                        "product_id": product["id"],
                        "variant_id": variant["id"]
                    }
        # pagination
        link = resp.links.get("next", {}).get("url")
        url = link if link else None
    return sku_map


def update_inventory(inventory_item_id, location_id, quantity):
    """Set inventory levels explicitly in Shopify."""
    payload = {
        "location_id": location_id,
        "inventory_item_id": inventory_item_id,
        "available": quantity
    }
    inv_url = f"{SHOP_URL}/inventory_levels/set.json"
    r = requests.post(inv_url, headers=shopify_headers, json=payload)
    if r.status_code != 200:
        print("Inventory update failed:", r.text)


def get_location_id():
    """Fetch the location ID of your Shopify store."""
    url = f"{SHOP_URL}/locations.json"
    resp = requests.get(url, headers=shopify_headers)
    if resp.status_code == 200:
        locations = resp.json().get("locations", [])
        if locations:
            return locations[0]["id"]
    return None


def main():
    # Fetch supplier products
    supplier_response = requests.get(SUPPLIER_API_URL, headers=supplier_headers)
    if supplier_response.status_code != 200:
        print("Supplier API request failed:", supplier_response.text)
        return

    supplier_products = supplier_response.json().get("products", [])
    sku_map = get_existing_products()
    location_id = get_location_id()

    for product in supplier_products:
        title = clean_text(product.get("body_html", ""))  # Swap supplier body_html → our title
        body_html = clean_text(product.get("title", ""))  # Swap supplier title → our body_html

        for variant in product.get("variants", []):
            sku = variant.get("sku", "")
            if not sku:
                continue

            payload = {
                "product": {
                    "title": title or "No Title",
                    "body_html": body_html,
                    "vendor": "",
                    "product_type": product.get("product_type", ""),
                    "tags": product.get("tags", ""),
                }
            }

            if sku in sku_map:
                # Update existing product
                product_id = sku_map[sku]["product_id"]
                url = f"{SHOP_URL}/products/{product_id}.json"
                response = requests.put(url, headers=shopify_headers, json=payload)
                if response.status_code == 200:
                    print(f"Updated product SKU: {sku}")
                else:
                    print(f"Failed to update product {sku}:", response.text)

                # Update inventory
                if location_id:
                    variant_id = sku_map[sku]["variant_id"]
                    # fetch inventory_item_id for this variant
                    variant_url = f"{SHOP_URL}/variants/{variant_id}.json"
                    variant_resp = requests.get(variant_url, headers=shopify_headers)
                    if variant_resp.status_code == 200:
                        inventory_item_id = variant_resp.json()["variant"]["inventory_item_id"]
                        update_inventory(inventory_item_id, location_id, variant.get("inventory_quantity", 0))
            else:
                # Create new product
                new_payload = {
                    "product": {
                        "title": title or "No Title",
                        "body_html": body_html,
                        "vendor": "",
                        "product_type": product.get("product_type", ""),
                        "tags": product.get("tags", ""),
                        "variants": [
                            {
                                "option1": variant.get("option1", ""),
                                "sku": sku,
                                "inventory_quantity": variant.get("inventory_quantity", 0),
                                "price": variant.get("price", "0.00"),
                                "inventory_management": "shopify"
                            }
                        ],
                        "images": [{"src": img["src"]} for img in product.get("images", [])] if product.get("images") else [],
                        "published": True
                    }
                }
                response = requests.post(f"{SHOP_URL}/products.json", headers=shopify_headers, json=new_payload)
                if response.status_code == 201:
                    new_product = response.json().get("product", {})
                    print(f"Created product: {new_product.get('title')}")
                else:
                    print("Failed to create product:", response.text)


if __name__ == "__main__":
    main()
