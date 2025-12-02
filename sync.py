import os
import json
import requests
import certifi  # add this

# --- Ensure requests uses a proper certificate bundle ---
os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()

# --- Environment variables ---
SUPPLIER_API_URL = os.environ["SUPPLIER_API_URL"]
SUPPLIER_TOKEN = os.environ["SUPPLIER_TOKEN"]
SHOPIFY_STORE = os.environ["SHOPIFY_STORE"]
SHOPIFY_TOKEN = os.environ["SHOPIFY_TOKEN"]

# --- Headers ---
supplier_headers = {
    "X-Shopify-Access-Token": SUPPLIER_TOKEN,
    "Accept": "application/json"
}

shopify_headers = {
    "X-Shopify-Access-Token": SHOPIFY_TOKEN,
    "Content-Type": "application/json"
}

# --- Fetch all supplier products ---
def fetch_all_supplier_products(limit=250):
    products = []
    since_id = 0

    while True:
        params = {"limit": limit, "since_id": since_id}
        response = requests.get(SUPPLIER_API_URL, headers=supplier_headers, params=params)

        if response.status_code != 200:
            print("❌ Supplier API error:", response.text)
            break

        batch = response.json().get("products", [])
        if not batch:
            break

        products.extend(batch)
        since_id = max([p["id"] for p in batch])

    return products

# --- Sync a single product to Shopify ---
def sync_product_to_shopify(product):
    if not product.get("variants"):
        print(f"⚠ Skipping {product.get('title', 'Unnamed Product')} - no variants")
        return

    handle = product.get("handle") or product.get("title", "product").lower().replace(" ", "-")

    payload = {
        "product": {
            "title": product.get("title", "Unnamed Product"),
            "body_html": product.get("body_html", ""),
            "vendor": product.get("vendor", "Default Vendor"),
            "handle": handle,
            "tags": product.get("tags", ""),
            "variants": [
                {
                    "option1": v.get("option1", "Default"),
                    "price": v.get("price", "0.00"),
                    "inventory_quantity": v.get("inventory_quantity", 0),
                    "sku": v.get("sku", ""),
                    "requires_shipping": v.get("requires_shipping", True)
                } for v in product.get("variants", [])
            ]
        }
    }

    url = f"https://{SHOPIFY_STORE}.myshopify.com/admin/api/2025-07/products.json"
    response = requests.post(url, headers=shopify_headers, json=payload)

    if response.status_code in (200, 201):
        print(f"✅ Synced: {product.get('title')}")
    else:
        print(f"❌ Failed to sync {product.get('title')}: {response.text}")

# --- Main ---
if __name__ == "__main__":
    print("📥 Fetching all supplier products...")
    products = fetch_all_supplier_products()
    print(f"✅ Total products received: {len(products)}")

    # Save raw JSON
    with open("supplier_raw.json", "w", encoding="utf-8") as f:
        json.dump(products, f, indent=2, ensure_ascii=False)
    print("📄 Saved full supplier JSON to supplier_raw.json")

    print("🔄 Starting Shopify sync...")
    for product in products:
        sync_product_to_shopify(product)

    print("✅ Shopify sync complete!")
