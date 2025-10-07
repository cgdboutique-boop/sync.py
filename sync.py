import requests
import json
import time

# ==============================
# CONFIGURATION
# ==============================
SHOPIFY_STORE = "https://yourstore.myshopify.com/admin/api/2024-10"
SHOPIFY_TOKEN = "your-shopify-access-token"
SUPPLIER_API = "https://example.com/supplier-feed"
SUPPLIER_TOKEN = "your-supplier-access-token"

VENDOR_NAME = "CGD Kids Boutique"

headers = {
    "Content-Type": "application/json",
    "X-Shopify-Access-Token": SHOPIFY_TOKEN
}

# ==============================
# HELPER FUNCTIONS
# ==============================
def get_shopify_products():
    print("📦 Fetching Shopify products...")
    products = []
    page = 1
    while True:
        url = f"{SHOPIFY_STORE}/products.json?limit=250&page={page}"
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            print(f"❌ Error fetching Shopify products: {response.status_code}")
            break
        data = response.json().get("products", [])
        if not data:
            break
        products.extend(data)
        page += 1
    print(f"✅ Found {len(products)} products on Shopify.")
    return products


def delete_duplicates(products):
    print("🧹 Checking for duplicates for vendor:", VENDOR_NAME)
    seen = {}
    duplicates = []
    for product in products:
        if product["vendor"] != VENDOR_NAME:
            continue
        sku = product["handle"].split("-")[-1]
        if sku in seen:
            duplicates.append(product)
        else:
            seen[sku] = product

    for dup in duplicates:
        product_id = dup["id"]
        title = dup["title"]
        try:
            delete_url = f"{SHOPIFY_STORE}/products/{product_id}.json"
            res = requests.delete(delete_url, headers=headers)
            if res.status_code == 200:
                print(f"🗑️ Deleted duplicate: {title} (ID: {product_id})")
            else:
                print(f"⚠️ Could not delete {title} (status {res.status_code})")
        except Exception as e:
            print(f"❌ Error deleting {title}: {e}")

    print(f"✅ Duplicate cleanup complete — {len(duplicates)} duplicates removed.")


def get_supplier_products():
    print("🔗 Fetching products from supplier...")
    try:
        response = requests.get(SUPPLIER_API, headers={"Authorization": f"Bearer {SUPPLIER_TOKEN}"})
        if response.status_code != 200:
            print(f"❌ Supplier fetch failed ({response.status_code})")
            return []
        return response.json().get("products", [])
    except Exception as e:
        print(f"❌ Error fetching supplier data: {e}")
        return []


def sync_product(product, existing=None):
    base_sku = product.get("sku")
    title = product.get("title")
    print(f"\n🔄 Syncing product for base SKU: {base_sku}")

    payload = {
        "product": {
            "title": title,
            "body_html": product.get("description", ""),
            "vendor": VENDOR_NAME,
            "handle": f"{title.lower().replace(' ', '-')}-{base_sku}",
            "status": "active",
            "variants": [
                {
                    "sku": base_sku,
                    "price": product.get("price", "0.00"),
                    "inventory_quantity": product.get("stock", 0)
                }
            ],
            "images": [{"src": img} for img in product.get("images", [])]
        }
    }

    max_retries = 3
    delay = 10  # seconds between retries

    for attempt in range(max_retries):
        try:
            if existing:
                url = f"{SHOPIFY_STORE}/products/{existing['id']}.json"
                response = requests.put(url, headers=headers, data=json.dumps(payload), timeout=90)
            else:
                url = f"{SHOPIFY_STORE}/products.json"
                response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=90)

            if response.status_code in [200, 201]:
                print(f"✅ Synced: {title} {base_sku}")
                break
            else:
                print(f"⚠️ Attempt {attempt+1}/{max_retries} failed ({response.status_code})")
        except requests.exceptions.RequestException as e:
            print(f"⚠️ Attempt {attempt+1}/{max_retries} error: {e}")

        if attempt < max_retries - 1:
            print(f"⏳ Retrying in {delay} seconds...")
            time.sleep(delay)
    else:
        print(f"❌ Failed to sync product {base_sku} after {max_retries} attempts.")


# ==============================
# MAIN SYNC FLOW
# ==============================
shopify_products = get_shopify_products()
delete_duplicates(shopify_products)
supplier_products = get_supplier_products()

if not supplier_products:
    print("⚠️ No supplier data available, skipping sync.")
else:
    print(f"🔁 Starting sync for {len(supplier_products)} products...")
    for prod in supplier_products:
        existing = next((p for p in shopify_products if p["handle"].endswith(prod["sku"])), None)
        sync_product(prod, existing)

print("\n✅ Sync complete — all possible products processed.")
