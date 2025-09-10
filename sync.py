import os
import requests
import time
import csv

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

LOG_FILE = "sync_log.csv"

# -------------------------------
# LOGGING FUNCTION
# -------------------------------
def log_action(action, sku, variant_id, inventory_item_id=None, old_value=None, new_value=None):
    with open(LOG_FILE, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), action, sku, variant_id, inventory_item_id, old_value, new_value])

# -------------------------------
# HELPER FUNCTIONS
# -------------------------------
def get_shopify_locations():
    r = requests.get(f"{SHOP_URL}/locations.json", headers=shopify_headers)
    r.raise_for_status()
    locations = r.json().get("locations", [])
    if not locations:
        raise Exception("No Shopify locations found.")
    return locations[0]["id"]

def fetch_all_shopify_variants():
    """Fetch all Shopify products and variants once using since_id pagination"""
    variants_by_sku = {}
    since_id = 0

    while True:
        url = f"{SHOP_URL}/products.json?limit=250&since_id={since_id}"
        r = requests.get(url, headers=shopify_headers)
        r.raise_for_status()
        products = r.json().get("products", [])
        if not products:
            break

        for product in products:
            for variant in product.get("variants", []):
                sku = variant.get("sku")
                if sku:
                    variants_by_sku[sku] = variant

        since_id = products[-1]["id"]
        time.sleep(0.5)  # pause to avoid rate limits

    return variants_by_sku

def update_variant_price(variant_id, sku, price):
    payload = {"variant": {"id": variant_id, "price": price}}
    r = requests.put(f"{SHOP_URL}/variants/{variant_id}.json", headers=shopify_headers, json=payload)
    r.raise_for_status()
    print(f"Updated price for variant {variant_id} (SKU {sku}) to {price}")
    log_action("Price Update", sku, variant_id, new_value=price)

def update_inventory(inventory_item_id, location_id, target_quantity, sku):
    # Get current quantity
    url = f"{SHOP_URL}/inventory_levels.json?inventory_item_ids={inventory_item_id}&location_ids={location_id}"
    r = requests.get(url, headers=shopify_headers)
    r.raise_for_status()
    levels = r.json().get("inventory_levels", [])

    if not levels:
        # Inventory item not linked to location — link it first
        connect_payload = {
            "location_id": location_id,
            "inventory_item_id": inventory_item_id,
            "available": 0
        }
        r_connect = requests.post(f"{SHOP_URL}/inventory_levels/connect.json", headers=shopify_headers, json=connect_payload)
        r_connect.raise_for_status()
        print(f"Connected inventory item {inventory_item_id} (SKU {sku}) to location")
        levels = [{"available": 0}]  # set current_quantity to 0 after connect

    current_quantity = levels[0]["available"] if levels[0]["available"] is not None else 0
    adjustment = target_quantity - current_quantity

    if adjustment == 0:
        print(f"Inventory for item {inventory_item_id} (SKU {sku}) is already correct ({current_quantity})")
        return

    payload = {
        "location_id": location_id,
        "inventory_item_id": inventory_item_id,
        "available_adjustment": adjustment
    }

    r_adjust = requests.post(f"{SHOP_URL}/inventory_levels/adjust.json", headers=shopify_headers, json=payload)
    r_adjust.raise_for_status()
    print(f"Adjusted inventory for item {inventory_item_id} (SKU {sku}) by {adjustment} to reach {target_quantity}")
    log_action("Inventory Adjust", sku, None, inventory_item_id, old_value=current_quantity, new_value=target_quantity)
    time.sleep(0.5)

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
    # Log creation
    for variant in product.get("variants", []):
        log_action("Product Created", variant.get("sku"), None, None, new_value=variant.get("inventory_quantity", 0))
    time.sleep(0.5)

# -------------------------------
# MAIN SYNC
# -------------------------------
def main():
    # Create CSV header
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Timestamp", "Action", "SKU", "Variant ID", "Inventory Item ID", "Old Value", "New Value"])

    location_id = get_shopify_locations()
    updated_inventory_items = set()

    # Fetch all Shopify variants once
    shopify_variants = fetch_all_shopify_variants()
    print(f"Fetched {len(shopify_variants)} existing Shopify variants by SKU")

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

            existing_variant = shopify_variants.get(sku)
            if existing_variant:
                # Update price
                update_variant_price(existing_variant["id"], sku, variant.get("price", "0.00"))
                # Update inventory once per inventory_item_id
                inventory_id = existing_variant["inventory_item_id"]
                if inventory_id not in updated_inventory_items:
                    update_inventory(inventory_id, location_id, variant.get("inventory_quantity", 0), sku)
                    updated_inventory_items.add(inventory_id)
                else:
                    print(f"Skipping duplicate inventory update for item {inventory_id}")
            else:
                create_product(product)

    print("\n✅ Full sync completed. Check sync_log.csv for details.")

if __name__ == "__main__":
    main()
