import os
import requests
import time

# -------------------------------
# CONFIG
# -------------------------------
SHOPIFY_STORE = os.environ.get("SHOPIFY_STORE")
SHOPIFY_TOKEN = os.environ.get("SHOPIFY_TOKEN")
SUPPLIER_API_URL = os.environ.get("SUPPLIER_API_URL")  # e.g. https://supplier.com/api/products
SUPPLIER_TOKEN = os.environ.get("SUPPLIER_TOKEN")

if not SHOPIFY_STORE or not SHOPIFY_TOKEN or not SUPPLIER_API_URL:
    raise ValueError("SHOPIFY_STORE, SHOPIFY_TOKEN, and SUPPLIER_API_URL must be set!")

SHOP_URL = f"https://{SHOPIFY_STORE}.myshopify.com/admin/api/2025-07"
shopify_headers = {
    "X-Shopify-Access-Token": SHOPIFY_TOKEN,
    "Content-Type": "application/json"
}

# -------------------------------
# SUPPLIER HEADERS (adjust to your supplier)
# Example options:
# 1) X-Auth-Token
# 2) Authorization: Bearer <token>
# 3) Authorization: Token <token>
# 4) No auth at all
# -------------------------------
SUPPLIER_HEADERS = {
    # Replace this with your supplier's required header
    "X-Auth-Token": SUPPLIER_TOKEN,
    "Accept": "application/json"
}

# -------------------------------
# HELPER FUNCTION
# -------------------------------
def request_with_retry(method, url, headers=None, json=None, max_retries=5):
    retry_delay = 2
    for attempt in range(max_retries):
        try:
            response = requests.request(method, url, headers=headers, json=json)
            if response.status_code in [429, 401, 422]:
                wait = int(response.headers.get("Retry-After", retry_delay))
                print(f"{response.status_code} from {url}. Retrying in {wait}s...")
                time.sleep(wait)
                retry_delay *= 2
                continue
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            print(f"Request error: {e}. Retrying in {retry_delay}s...")
            time.sleep(retry_delay)
            retry_delay *= 2
    return None

# -------------------------------
# FETCH SUPPLIER PRODUCT
# -------------------------------
def fetch_supplier_product(sku):
    """Fetch product data from supplier API."""
    url = f"{SUPPLIER_API_URL}/{sku}"
    r = request_with_retry("GET", url, headers=SUPPLIER_HEADERS)
    if not r:
        raise RuntimeError(f"❌ Failed to fetch supplier product {sku}")
    return r.json()

# -------------------------------
# GET SHOPIFY LOCATION
# -------------------------------
def get_shopify_location_id():
    r = request_with_retry("GET", f"{SHOP_URL}/locations.json", headers=shopify_headers)
    if not r:
        raise RuntimeError("❌ Could not fetch Shopify locations")
    locations = r.json().get("locations", [])
    if not locations:
        raise RuntimeError("❌ No Shopify locations found")
    return locations[0]["id"]

# -------------------------------
# SYNC PRODUCT
# -------------------------------
def sync_product(sku):
    # 1️⃣ Fetch supplier product
    supplier_data = fetch_supplier_product(sku)

    # 2️⃣ Map supplier fields → Shopify
    title = supplier_data.get("title", f"Product {sku}")
    body_html = supplier_data.get("description", "")
    vendor = supplier_data.get("vendor", "THE BRAVE ONES CHILDRENS FASHION")
    product_type = supplier_data.get("category", "General")
    tags = ",".join(supplier_data.get("tags", []))

    supplier_variants = supplier_data.get("variants", [])
    supplier_images = supplier_data.get("images", [])

    # 3️⃣ Check if product exists in Shopify
    r = request_with_retry("GET", f"{SHOP_URL}/products.json?handle={sku}", headers=shopify_headers)
    existing_products = r.json().get("products", []) if r else []

    product_data = {
        "product": {
            "title": title,
            "body_html": body_html,
            "vendor": vendor,
            "product_type": product_type,
            "tags": tags,
            "handle": sku
        }
    }

    if existing_products:
        product_id = existing_products[0]["id"]
        print(f"🔄 Updating existing product {sku}")
        r = request_with_retry("PUT", f"{SHOP_URL}/products/{product_id}.json", headers=shopify_headers, json=product_data)
        shop_product = r.json()["product"]
    else:
        print(f"➕ Creating new product {sku}")
        product_data["product"]["variants"] = [
            {"option1": v["option"], "sku": v["sku"], "price": v["price"], "inventory_management": "shopify"} for v in supplier_variants
        ]
        product_data["product"]["images"] = [{"src": img} for img in supplier_images]
        r = request_with_retry("POST", f"{SHOP_URL}/products.json", headers=shopify_headers, json=product_data)
        shop_product = r.json()["product"]

    # 4️⃣ Update inventory for each variant
    location_id = get_shopify_location_id()
    shop_variants = {v["sku"]: v for v in shop_product["variants"]}

    for sv in supplier_variants:
        sku_code = sv["sku"]
        stock = sv.get("stock", 0)
        shop_v = shop_variants.get(sku_code)
        if not shop_v:
            print(f"⚠️ Shopify variant missing for {sku_code}")
            continue
        inventory_item_id = shop_v["inventory_item_id"]
        payload = {
            "location_id": location_id,
            "inventory_item_id": inventory_item_id,
            "available": stock
        }
        request_with_retry("POST", f"{SHOP_URL}/inventory_levels/set.json", headers=shopify_headers, json=payload)
        print(f"   ✅ Stock updated for {sku_code} → {stock}")

    # 5️⃣ Update variant prices if changed
    for sv in supplier_variants:
        sku_code = sv["sku"]
        price = sv["price"]
        shop_v = shop_variants.get(sku_code)
        if shop_v and str(shop_v.get("price")) != str(price):
            request_with_retry(
                "PUT",
                f"{SHOP_URL}/variants/{shop_v['id']}.json",
                headers=shopify_headers,
                json={"variant": {"id": shop_v["id"], "price": price}}
            )
            print(f"   💰 Price updated for {sku_code} → {price}")

    # 6️⃣ Update images if needed
    if supplier_images:
        request_with_retry(
            "PUT",
            f"{SHOP_URL}/products/{shop_product['id']}.json",
            headers=shopify_headers,
            json={"product": {"images": [{"src": img} for img in supplier_images]}}
        )
        print(f"   🖼️ Images updated for {sku}")

    print(f"✅ Finished syncing product {sku}")

# -------------------------------
# RUN
# -------------------------------
if __name__ == "__main__":
    sync_product("2000133")
