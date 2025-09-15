import os
import requests
import time

# -------------------------------
# CONFIG
# -------------------------------
SHOPIFY_STORE = os.environ.get("SHOPIFY_STORE")
SHOPIFY_TOKEN = os.environ.get("SHOPIFY_TOKEN")
SUPPLIER_API_URL = os.environ.get("SUPPLIER_API_URL")  # e.g. https://supplier.com/api/products/{sku}
SUPPLIER_TOKEN = os.environ.get("SUPPLIER_TOKEN")

if not SHOPIFY_STORE or not SHOPIFY_TOKEN:
    raise ValueError("SHOPIFY_STORE or SHOPIFY_TOKEN is not set!")

SHOP_URL = f"https://{SHOPIFY_STORE}.myshopify.com/admin/api/2025-07"
shopify_headers = {
    "X-Shopify-Access-Token": SHOPIFY_TOKEN,
    "Content-Type": "application/json"
}

supplier_headers = {
    "Authorization": f"Bearer {SUPPLIER_TOKEN}",
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
# SUPPLIER FETCH
# -------------------------------
def fetch_supplier_product(sku):
    url = f"{SUPPLIER_API_URL}/{sku}"
    r = request_with_retry("GET", url, headers=supplier_headers)
    if r:
        return r.json()
    else:
        print(f"❌ Error: Could not fetch supplier product {sku}")
        return None

# -------------------------------
# SYNC PRODUCT
# -------------------------------
def sync_product(sku):
    supplier_data = fetch_supplier_product(sku)
    if not supplier_data:
        return

    # Example supplier JSON format
    title = supplier_data["title"]
    body_html = supplier_data.get("description", "")
    vendor = supplier_data.get("vendor", "THE BRAVE ONES CHILDRENS FASHION")
    product_type = supplier_data.get("category", "Default")
    tags = ",".join(supplier_data.get("tags", []))

    variants_data = supplier_data.get("variants", [])
    images_data = supplier_data.get("images", [])

    # Step 1: Find Shopify product by handle
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

        # Step 2: Update product details
        request_with_retry("PUT", f"{SHOP_URL}/products/{product_id}.json", headers=shopify_headers, json=product_data)

        # Step 3: Update variants
        shopify_variants = {v["sku"]: v for v in existing_products[0]["variants"]}
        for variant in variants_data:
            sku_code = variant["sku"]
            if sku_code in shopify_variants:
                shopify_variant = shopify_variants[sku_code]

                # Update price
                request_with_retry(
                    "PUT",
                    f"{SHOP_URL}/variants/{shopify_variant['id']}.json",
                    headers=shopify_headers,
                    json={"variant": {"id": shopify_variant["id"], "price": variant["price"]}}
                )

                # Update inventory level
                inventory_item_id = shopify_variant["inventory_item_id"]
                location_r = request_with_retry("GET", f"{SHOP_URL}/locations.json", headers=shopify_headers)
                location_id = location_r.json()["locations"][0]["id"]

                request_with_retry(
                    "POST",
                    f"{SHOP_URL}/inventory_levels/set.json",
                    headers=shopify_headers,
                    json={
                        "location_id": location_id,
                        "inventory_item_id": inventory_item_id,
                        "available": variant["quantity"]
                    }
                )

        # Step 4: Update images
        if images_data:
            request_with_retry(
                "PUT",
                f"{SHOP_URL}/products/{product_id}.json",
                headers=shopify_headers,
                json={"product": {"images": [{"src": img} for img in images_data]}}
            )

        print(f"✅ Updated product: {sku}")
    else:
        print(f"➕ Creating new product {sku}")

        product_data["product"]["variants"] = [
            {"option1": v["option"], "sku": v["sku"], "price": v["price"]} for v in variants_data
        ]
        product_data["product"]["images"] = [{"src": img} for img in images_data]

        r = request_with_retry("POST", f"{SHOP_URL}/products.json", headers=shopify_headers, json=product_data)
        if r:
            print(f"✅ Created product: {sku}")
        else:
            print(f"❌ Failed to create product: {sku}")

# -------------------------------
# RUN
# -------------------------------
if __name__ == "__main__":
    sync_product("2000133")
