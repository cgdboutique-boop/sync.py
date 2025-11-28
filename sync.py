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

VENDOR_NAME = "CGD Kids Boutique"

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

```
    data = response.json().get("products", [])
    if not data:
        break

    products.extend(data)
    print(f"📥 Fetched {len(data)} products from supplier (since_id: {since_id})")
    since_id = max([p.get("id", 0) for p in data])
print(f"✅ Total supplier products fetched: {len(products)}")
return products
```

# ----------------------------

# Fetch existing Shopify products for vendor

# ----------------------------

def fetch_shopify_vendor_products(vendor_name):
products = []
page = 1
while True:
url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products.json?vendor={vendor_name}&limit=250&page={page}"
response = requests.get(url, headers=shopify_headers)
if response.status_code != 200:
print(f"❌ Shopify fetch error: {response.text}")
break
data = response.json().get("products", [])
if not data:
break
products.extend(data)
page += 1
print(f"✅ Total Shopify products fetched for vendor '{vendor_name}': {len(products)}")
return products

# ----------------------------

# Delete duplicate products by SKU or handle (vendor only)

# ----------------------------

def delete_duplicates(products):
sku_map = defaultdict(list)
handle_map = defaultdict(list)

```
for p in products:
    handle = p.get("handle")
    for v in p.get("variants", []):
        sku = v.get("sku")
        if sku:
            sku_map[sku].append(p)
    if handle:
        handle_map[handle].append(p)

# Delete duplicate SKUs
for sku, plist in sku_map.items():
    if len(plist) > 1:
        keep = plist[0]
        to_delete = plist[1:]
        for pd in to_delete:
            delete_product(pd["id"], sku)

# Delete duplicate Handles
for handle, plist in handle_map.items():
    if len(plist) > 1:
        keep = plist[0]
        to_delete = plist[1:]
        for pd in to_delete:
            delete_product(pd["id"], handle)
```

def delete_product(product_id, identifier):
url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products/{product_id}.json"
response = requests.delete(url, headers=shopify_headers)
if response.status_code == 200 or response.status_code == 204:
print(f"✅ Deleted duplicate product: {identifier}")
else:
print(f"❌ Failed to delete product {identifier}: {response.text}")

# ----------------------------

# Main sync logic

# ----------------------------

def sync_products():
supplier_products = fetch_supplier_products()
shopify_products = fetch_shopify_vendor_products(VENDOR_NAME)
delete_duplicates(shopify_products)

```
sku_groups = defaultdict(list)

for product in supplier_products:
    for v in product.get("variants", []):
        sku = v.get("sku")
        if not sku or not isinstance(sku, str):
            continue
        sku = sku.replace("#", "").strip()
        if "(200)" in sku or not sku:
            continue
        base_sku = sku.split(" ")[0]
        sku_groups[base_sku].append((product, v))

synced_handles = []

for base_sku, items in sku_groups.items():
    print(f"\n🔄 Syncing product for base SKU: {base_sku}")

    # Reference product
    product, _ = items[0]
    title = product.get("title", "").replace("#", "").strip()
    body_html = product.get("body_html", "")
    vendor = VENDOR_NAME
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
        sku = v.get("sku")
        if not sku:
            continue
        v["sku"] = sku.replace("#", "").strip()
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

    # Check if product exists by handle
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

print("\n📊 Duplicate Handle Check Report")
counts = Counter(synced_handles)
for handle, count in counts.items():
    if count > 1:
        print(f"⚠️ Duplicate detected: {handle} synced {count} times")
```

# ----------------------------

# Run sync

# ----------------------------

if **name** == "**main**":
sync_products()
