import os
import requests
import time

# -------------------------------
# CONFIG
# -------------------------------
SHOP_URL = "https://cgdboutique.myshopify.com/admin/api/2023-10"
SHOPIFY_TOKEN = os.getenv("SHOPIFY_TOKEN")
shopify_headers = {
    "X-Shopify-Access-Token": SHOPIFY_TOKEN,
    "Content-Type": "application/json"
}

SUPPLIER_API_URL = "https://the-brave-ones-childrens-fashion.myshopify.com/admin/api/2023-10/products.json"
SUPPLIER_TOKEN = os.getenv("SUPPLIER_TOKEN")
supplier_headers = {
    "X-Shopify-Access-Token": SUPPLIER_TOKEN,
    "Content-Type": "application/json"
}

# -------------------------------
# HELPER FUNCTIONS
# -------------------------------
def get_shopify_locations():
    r = requests.get(f"{SHOP_URL}/locations.json", headers=shopify_headers)
    r.raise_for_status()
    locations = r.json().get("locations", [])
    if not locations:
        raise Exception("No Shopify locations found. Check API permissions.")
    return locations[0]["id"]  # use first location

def find_variant_by_sku(sku):
    r = requests.get(f"{SHOP_URL}/variants.json?sku={sku}", headers=shopify_headers)
    r.raise_for_status()
    variants = r.json().get("variants", [])
    return variants[0] if variants else None

def update_variant_price(variant_id, price):
    payload = {"variant": {"id": variant_id, "price": price}}
    r = requests.put(f"{SHOP_URL}/variants/{variant_id}.json", headers=shopify_headers, json=payload)
    r.raise_for_status()
    print(f"Updated price for variant {variant_id} to {price}")

def update_inventory(inventory_item_id, location_id, quantity):
    payload = {
        "location_id": location_id,
        "inventory_item_id": inventory_item_id,
        "available": quantity
    }
    r = requests.post(f"{SHOP_URL}/inventory_levels/set.json", headers=shopify_headers, json=payload)
    r.raise_for_status()
    print(f"Updated inventory for item {inventory_item_id} to {quantity}")

def create_product(product):
    variants = []
    for variant in product.get("variants", []):
        variants.append({
            "option1": variant.get("option1", ""),
            "sku": variant.get("sku", ""),
            "price": variant.get("price", "0.00"),
            "inventory_quantity": variant.get("inventory_quantity", 0)
        })

    images = [{"src": img["src"]} for img in product.get("images", [])] if product.get("images") else []

    payload = {
        "product": {
            "title": product.get("title", "No Title"),
            "body_html": product.get("body_html", ""),
            "vendor": product.get("vendor", ""),
            "product_type": product.get("product_type", ""),
            "tags": ",".join(product.get("tags", [])) if isinstance(product.get("tags"), list) else product.get("tags", ""),
            "variants": variants,
            "images": images,
            "published": True
        }
    }
    r = requests.post(f"{SHOP_URL}/products.json", headers=shopify_headers, json=payload)
    r.raise_for_status()
    print(f"Created new product: {product.get('title')}")
    time.sleep(0.5)  # pause to avoid hitting rate limit

# -------------------------------
# MAIN SYNC PROCESS
# -------------------------------
def main():
    location_id = get_shopify_locations()
    updated_inventory_items = set()  # track inventory items already updated

    # Fetch supplier products
    r = requests.get(SUPPLIER_API_URL, headers=supplier_headers)
    r.raise_for_status()
    supplier_products = r.json().get("products", [])
    print(f"Fetched {len(supplier_products)} supplier products")

    for product in supplier_products:
        for variant in product.get("variants", []):
            sku = variant.get("sku")
            if not sku:
                print(f"Skipping variant with no SKU in product {product.get('title')}")
                continue

            existing_variant = find_variant_by_sku(sku)
            if existing_variant:
                # Update price
                update_variant_price(existing_variant["id"], variant.get("price", "0.00"))
                # Update inventory only once per inventory_item_id
                inventory_id = existing_variant["inventory_item_id"]
                if inventory_id not in updated_inventory_items:
                    update_inventory(inventory_id, location_id, variant.get("inventory_quantity", 0))
                    updated_inventory_items.add(inventory_id)
                    time.sleep(0.5)  # small delay to avoid 429
                else:
                    print(f"Skipping duplicate inventory update for item {inventory_id}")
            else:
                # Product doesn’t exist → create new product
                create_product(product)

    print("\n✅ Full sync completed.")

if __name__ == "__main__":
    main()
