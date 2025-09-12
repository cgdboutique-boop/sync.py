import os
import requests
import time

# Shopify API
shopify_store = os.getenv("SHOPIFY_STORE")
shopify_token = os.getenv("SHOPIFY_TOKEN")
shopify_url = f"https://{shopify_store}/admin/api/2025-07/products.json"
shopify_headers = {
    "X-Shopify-Access-Token": shopify_token,
    "Content-Type": "application/json"
}

# Supplier API
supplier_api_url = os.getenv("SUPPLIER_API_URL")
supplier_token = os.getenv("SUPPLIER_TOKEN")
supplier_headers = {"Authorization": f"Bearer {supplier_token}"}

# --- Helpers ---
def get_supplier_products(page=1, per_page=100):
    """Fetch one batch of products from supplier API"""
    url = f"{supplier_api_url}?page={page}&per_page={per_page}"
    r = requests.get(url, headers=supplier_headers)
    r.raise_for_status()
    return r.json()

def find_shopify_product_by_sku(sku):
    """Search Shopify for product with matching SKU"""
    url = f"{shopify_url}?handle={sku}"
    r = requests.get(url, headers=shopify_headers)
    r.raise_for_status()
    products = r.json().get("products", [])
    return products[0] if products else None

def create_shopify_product(product):
    """Create new product in Shopify"""
    payload = {"product": {
        "title": product["name"],
        "body_html": product.get("description", ""),
        "variants": [{"sku": product["sku"], "price": product.get("price", "0")}]
    }}
    r = requests.post(shopify_url, headers=shopify_headers, json=payload)
    r.raise_for_status()
    print(f"✅ Created product {product['sku']}")

def update_shopify_product(shopify_product, product):
    """Update existing Shopify product"""
    product_id = shopify_product["id"]
    url = f"https://{shopify_store}/admin/api/2025-07/products/{product_id}.json"
    payload = {"product": {
        "id": product_id,
        "title": product["name"],
        "body_html": product.get("description", "")
    }}
    r = requests.put(url, headers=shopify_headers, json=payload)
    r.raise_for_status()
    print(f"🔄 Updated product {product['sku']}")

# --- Main sync ---
def sync_products():
    page = 1
    total_synced = 0

    while True:
        products = get_supplier_products(page)
        if not products:
            print("🎉 Finished syncing all supplier products")
            break

        for product in products:
            sku = product.get("sku")
            if not sku:
                continue

            shopify_product = find_shopify_product_by_sku(sku)
            if shopify_product:
                update_shopify_product(shopify_product, product)
            else:
                create_shopify_product(product)

            total_synced += 1
            if total_synced % 100 == 0:
                print(f"⏳ Synced {total_synced} products so far...")

            time.sleep(0.5)  # to respect API rate limits

        print(f"✅ Finished batch {page} ({len(products)} products)")
        page += 1

if __name__ == "__main__":
    sync_products()
