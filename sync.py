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
    # Remove <p>, </p>, Â, <span>, <span data-mce-fragment="1">
    cleaned = re.sub(r"<\/?p>|Â|<\/?span.*?>", "", text)
    return cleaned.strip()


def get_existing_skus():
    """Fetch all existing SKUs from Shopify to prevent duplicates."""
    existing_skus = set()
    url = f"{SHOP_URL}/products.json?limit=250"
    while url:
        resp = requests.get(url, headers=shopify_headers).json()
        products = resp.get("products", [])
        for product in products:
            for variant in product.get("variants", []):
                if variant.get("sku"):
                    existing_skus.add(variant["sku"])
        # Pagination
        link = resp.get("link")
        url = None
        if link and 'rel="next"' in link:
            url = link.split(";")[0].strip("<>")
    return existing_skus


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
    existing_skus = get_existing_skus()
    location_id = get_location_id()

    for product in supplier_products:
        title = clean_text(product.get("body_html", ""))  # Swap: supplier body_html → our title
        body_html = clean_text(product.get("title", ""))  # Swap: supplier title → our body_html

        variants = []
        for variant in product.get("variants", []):
            sku = variant.get("sku", "")
            if not sku:
                continue
            if sku in existing_skus:
                print(f"Skipping duplicate SKU: {sku}")
                continue

            variants.append({
                "option1": variant.get("option1", ""),
                "sku": sku,
                "inventory_quantity": variant.get("inventory_quantity", 0),
                "price": variant.get("price", "0.00"),
                "inventory_management": "shopify"  # Ensure inventory is tracked
            })

        if not variants:
            continue

        images = [{"src": img["src"]} for img in product.get("images", [])] if product.get("images") else []

        payload = {
            "product": {
                "title": title or "No Title",
                "body_html": body_html,
                "vendor": "",  # remove vendor
                "product_type": product.get("product_type", ""),
                "tags": product.get("tags", ""),
                "variants": variants,
                "images": images,
                "published": True
            }
        }

        response = requests.post(f"{SHOP_URL}/products.json", headers=shopify_headers, json=payload)
        if response.status_code == 201:
            new_product = response.json().get("product", {})
            print(f"Created product: {new_product.get('title')}")

            # Update inventory for each variant
            if location_id:
                for variant in new_product.get("variants", []):
                    update_inventory(
                        variant["inventory_item_id"],
                        location_id,
                        variant.get("inventory_quantity", 0)
                    )
        else:
            print("Failed to create product:", response.text)


if __name__ == "__main__":
    main()

