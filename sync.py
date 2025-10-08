import os
import json
import time
import requests
from collections import defaultdict, Counter

# ----------------------------
# Load secrets from environment
# ----------------------------
SHOPIFY_STORE = os.environ["SHOPIFY_STORE"]
SHOPIFY_TOKEN = os.environ["SHOPIFY_TOKEN"]
SUPPLIER_API_URL = os.environ["SUPPLIER_API_URL"]
SUPPLIER_TOKEN = os.environ["SUPPLIER_TOKEN"]

# ----------------------------
# Headers
# ----------------------------
supplier_headers = {
    "X-Shopify-Access-Token": SUPPLIER_TOKEN,
    "Accept": "application/json"
}

shopify_headers = {
    "X-Shopify-Access-Token": SHOPIFY_TOKEN,
    "Content-Type": "application/json"
}

# ----------------------------
# Helper: rate-limited request
# ----------------------------
def safe_request(method, url, **kwargs):
    """Make a Shopify API call with automatic rate-limit handling."""
    while True:
        response = requests.request(method, url, **kwargs)
        if response.status_code == 429:
            print("⚠️ Rate limit hit. Pausing for 1 second...")
            time.sleep(1)
            continue
        time.sleep(0.6)  # ~1.5 requests/sec average
        return response

# ----------------------------
# Fetch supplier products using since_id pagination
# ----------------------------
def fetch_supplier_products(limit=250):
    products = []
    since_id = 0
    while True:
        params = {"limit": limit, "since_id": since_id}
        response = safe_request("GET", SUPPLIER_API_URL, headers=supplier_headers, params=params)
        if response.status_code != 200:
            print(f"❌ Supplier API error (since_id {since_id}): {response.text}")
            break

        data = response.json().get("products", [])
        if not data:
            break

        products.extend(data)
        print(f"📥 Fetched {len(data)} products from supplier (since_id: {since_id})")
        since_id = max([p["id"] for p in data])

    print(f"✅ Total supplier products fetched: {len(products)}")
    return products

# ----------------------------
# Check if SKU already exists on Shopify
# ----------------------------
def shopify_product_exists_by_sku(sku):
    url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products.json?sku={sku}"
    response = safe_request("GET", url, headers=shopify_headers)
    if response.status_code == 200:
        products = response.json().get("products", [])
        return len(products) > 0
    return False

# ----------------------------
# Main sync logic
# ----------------------------
def sync_products():
    products = fetch_supplier_products()
    sku_groups = defaultdict(list)

    for product in products:
        for v in product.get("variants", []):
            if not isinstance(v, dict):
                continue
            sku = v.get("sku")
            if not isinstance(sku, str):
                continue
            sku = sku.replace("#", "").strip()
            if "(200)" in sku or not sku:
                continue
            base_sku = sku.split(" ")[0]
            sku_groups[base_sku].append((product, v))

    synced_handles = []

    for base_sku, items in sku_groups.items():
        print(f"\n🔄 Syncing product for base SKU: {base_sku}")

        # Skip duplicate creation if same SKU already exists
        if shopify_product_exists_by_sku(base_sku):
            print(f"⚠️ Product {base_sku} already exists on Shopify — skipping duplicate creation.")
            continue

        # Reference product
        product, _ = items[0]
        title = product.get("title", "").replace("#", "").strip()
        body_html = product.get("body_html", "")
        vendor = "CGD Kids Boutique"
        product_type = product.get("product_type", "")
        tags = product.get("tags", "")
        status = product.get("status", "active")
        images = product.get("images", [])

        # Clean images
        for img in images:
            if not isinstance(img, dict):
                continue
            for key in ["id", "product_id", "admin_graphql_api_id", "created_at", "updated_at"]:
                img.pop(key, None)

        # Build variants
        valid_variants = []
        option_values = []

        for _, v in items:
            v["sku"] = v.get("sku", "").replace("#", "").strip()
            v["inventory_management"] = "shopify"
            v["inventory_policy"] = "deny"
            v["price"] = v.get("price", "0.00")
            v["inventory_quantity"] = v.get("inventory_quantity", 0)
            v["option1"] = v.get("option1", "").strip()
            for key in ["id", "product_id", "inventory_item_id", "admin_graphql_api_id", "created_at", "updated_at"]:
                v.pop(key, None)
            valid_variants.append(v)
            option_values.append(v["option1"])

        options = [{"name": "Size", "values": option_values}]
        handle = base_sku.lower().strip()

        # Build payload
        payload = {
            "product": {
                "title": title,
                "body_html": body_html,
                "vendor": vendor,
                "product_type": product_type,
                "handle": handle,
                "tags": tags,
                "status": status,
                "options": options,
                "variants": valid_variants,
                "images": images
            }
        }

        # Check if handle already exists (backup)
        check_url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products.json?handle={handle}"
        check_response = safe_request("GET", check_url, headers=shopify_headers)
        existing = check_response.json().get("products", [])

        if existing:
            product_id = existing[0]["id"]
            payload["product"]["id"] = product_id
            update_url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products/{product_id}.json"
            print(f"🔄 Updating existing product: {handle}")
            response = safe_request("PUT", update_url, headers=shopify_headers, data=json.dumps(payload))
        else:
            create_url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products.json"
            print(f"🆕 Creating new product: {handle}")
            response = safe_request("POST", create_url, headers=shopify_headers, data=json.dumps(payload))

        try:
            print("📦 Shopify response:")
            print(json.dumps(response.json(), indent=2))
        except Exception:
            print("❌ Failed to parse Shopify response:")
            print(response.text)

        if response.status_code in [200, 201]:
            print(f"✅ Synced: {title}")
            synced_handles.append(handle)
        else:
            print(f"❌ Failed to sync: {title} ({response.status_code})")

    # ----------------------------
    # Duplicate check report
    # ----------------------------
    print("\n📊 Duplicate Handle Check Report")
    counts = Counter(synced_handles)
    for handle, count in counts.items():
        if count > 1:
            print(f"⚠️ Duplicate detected: {handle} synced {count} times")

# ----------------------------
# Run sync
# ----------------------------
if __name__ == "__main__":
    sync_products()
import os
import json
import requests
from collections import defaultdict, Counter

# ----------------------------
# Load secrets from environment
# ----------------------------
SHOPIFY_STORE = os.environ["SHOPIFY_STORE"]
SHOPIFY_TOKEN = os.environ["SHOPIFY_TOKEN"]
SUPPLIER_API_URL = os.environ["SUPPLIER_API_URL"]
SUPPLIER_TOKEN = os.environ["SUPPLIER_TOKEN"]

# ----------------------------
# Headers
# ----------------------------
supplier_headers = {
    "X-Shopify-Access-Token": SUPPLIER_TOKEN,
    "Accept": "application/json"
}

shopify_headers = {
    "X-Shopify-Access-Token": SHOPIFY_TOKEN,
    "Content-Type": "application/json"
}

# ----------------------------
# Fetch supplier products using since_id pagination
# ----------------------------
def fetch_supplier_products(limit=250):
    products = []
    since_id = 0
    while True:
        params = {"limit": limit, "since_id": since_id}
        response = requests.get(SUPPLIER_API_URL, headers=supplier_headers, params=params)
        if response.status_code != 200:
            print(f"❌ Supplier API error (since_id {since_id}): {response.text}")
            break

        data = response.json().get("products", [])
        if not data:
            break

        products.extend(data)
        print(f"📥 Fetched {len(data)} products from supplier (since_id: {since_id})")
        since_id = max([p["id"] for p in data])

    print(f"✅ Total supplier products fetched: {len(products)}")
    return products

# ----------------------------
# Check if SKU already exists on Shopify
# ----------------------------
def shopify_product_exists_by_sku(sku):
    url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products.json?sku={sku}"
    response = requests.get(url, headers=shopify_headers)
    if response.status_code == 200:
        products = response.json().get("products", [])
        return len(products) > 0
    return False

# ----------------------------
# Main sync logic
# ----------------------------
def sync_products():
    products = fetch_supplier_products()
    sku_groups = defaultdict(list)

    for product in products:
        for v in product.get("variants", []):
            if not isinstance(v, dict):
                continue
            sku = v.get("sku")
            if not isinstance(sku, str):
                continue
            sku = sku.replace("#", "").strip()
            if "(200)" in sku or not sku:
                continue
            base_sku = sku.split(" ")[0]
            sku_groups[base_sku].append((product, v))

    synced_handles = []

    for base_sku, items in sku_groups.items():
        print(f"\n🔄 Syncing product for base SKU: {base_sku}")

        # Skip duplicate creation if same SKU already exists on Shopify
        if shopify_product_exists_by_sku(base_sku):
            print(f"⚠️ Product {base_sku} already exists on Shopify — skipping duplicate creation.")
            continue

        # Reference product
        product, _ = items[0]
        title = product.get("title", "").replace("#", "").strip()
        body_html = product.get("body_html", "")
        vendor = "CGD Kids Boutique"
        product_type = product.get("product_type", "")
        tags = product.get("tags", "")
        status = product.get("status", "active")
        images = product.get("images", [])

        # Clean images
        for img in images:
            if not isinstance(img, dict):
                continue
            for key in ["id", "product_id", "admin_graphql_api_id", "created_at", "updated_at"]:
                img.pop(key, None)

        # Build variants
        valid_variants = []
        option_values = []

        for _, v in items:
            v["sku"] = v.get("sku", "").replace("#", "").strip()
            v["inventory_management"] = "shopify"
            v["inventory_policy"] = "deny"
            v["price"] = v.get("price", "0.00")
            v["inventory_quantity"] = v.get("inventory_quantity", 0)
            v["option1"] = v.get("option1", "").strip()
            for key in ["id", "product_id", "inventory_item_id", "admin_graphql_api_id", "created_at", "updated_at"]:
                v.pop(key, None)
            valid_variants.append(v)
            option_values.append(v["option1"])

        options = [{"name": "Size", "values": option_values}]
        handle = base_sku.lower().strip()

        # Build payload
        payload = {
            "product": {
                "title": title,
                "body_html": body_html,
                "vendor": vendor,
                "product_type": product_type,
                "handle": handle,
                "tags": tags,
                "status": status,
                "options": options,
                "variants": valid_variants,
                "images": images
            }
        }

        # Check if handle already exists (as backup)
        check_url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products.json?handle={handle}"
        check_response = requests.get(check_url, headers=shopify_headers)
        existing = check_response.json().get("products", [])

        if existing:
            product_id = existing[0]["id"]
            payload["product"]["id"] = product_id
            update_url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products/{product_id}.json"
            print(f"🔄 Updating existing product: {handle}")
            response = requests.put(update_url, headers=shopify_headers, data=json.dumps(payload))
        else:
            create_url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products.json"
            print(f"🆕 Creating new product: {handle}")
            response = requests.post(create_url, headers=shopify_headers, data=json.dumps(payload))

        try:
            print("📦 Shopify response:")
            print(json.dumps(response.json(), indent=2))
        except Exception:
            print("❌ Failed to parse Shopify response:")
            print(response.text)

        if response.status_code in [200, 201]:
            print(f"✅ Synced: {title}")
            synced_handles.append(handle)
        else:
            print(f"❌ Failed to sync: {title} ({response.status_code})")

    # ----------------------------
    # Duplicate check report
    # ----------------------------
    print("\n📊 Duplicate Handle Check Report")
    counts = Counter(synced_handles)
    for handle, count in counts.items():
        if count > 1:
            print(f"⚠️ Duplicate detected: {handle} synced {count} times")

# ----------------------------
# Run sync
# ----------------------------
if __name__ == "__main__":
    sync_products()
