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

# Fetch Shopify products for vendor

# ----------------------------

def fetch_shopify_products(vendor="CGD Kids Boutique"):
products = []
url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products.json?vendor={vendor}&limit=250"
while url:
resp = requests.get(url, headers=shopify_headers)
if resp.status_code != 200:
print(f"❌ Shopify API error: {resp.text}")
break
data = resp.json().get("products", [])
products.extend(data)
link_header = resp.headers.get("Link")
if link_header and 'rel="next"' in link_header:
url = link_header.split("<")[1].split(">")[0]
else:
url = None
print(f"✅ Total Shopify products fetched for vendor '{vendor}': {len(products)}")
return products

# ----------------------------

# Main sync logic

# ----------------------------

def sync_products():
supplier_products = fetch_supplier_products()
shopify_products = fetch_shopify_products()
shopify_handle_map = {p["handle"]: p for p in shopify_products}

```
sku_groups = defaultdict(list)
for product in supplier_products:
    for v in product.get("variants", []):
        if not isinstance(v, dict):
            continue
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
        v_sku = v.get("sku")
        if not v_sku:
            continue
        v["sku"] = v_sku.replace("#", "").strip()
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

    # Check if product exists for this vendor
    existing_product = shopify_handle_map.get(handle)
    if existing_product and existing_product.get("vendor") == vendor:
        product_id = existing_product["id"]
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
# Duplicate cleanup for this vendor
# ----------------------------
print("\n📊 Checking for duplicates (handle & SKU) for vendor only")
vendor_products = [p for p in shopify_products if p.get("vendor") == "CGD Kids Boutique"]
sku_map = defaultdict(list)
for p in vendor_products:
    for v in p.get("variants", []):
        sku_map[v.get("sku", "")].append((p["id"], v["id"]))

for sku, variants in sku_map.items():
    if len(variants) > 1:
        # Keep latest (highest variant ID)
        variants.sort(key=lambda x: x[1], reverse=True)
        to_delete = variants[1:]
        for pid, vid in to_delete:
            del_url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products/{pid}/variants/{vid}.json"
            print(f"🗑 Deleting duplicate SKU {sku} variant {vid} from product {pid}")
            requests.delete(del_url, headers=shopify_headers)

print("✅ Duplicate cleanup complete for vendor: CGD Kids Boutique")
```

# ----------------------------

# Run sync

# ----------------------------

if **name** == "**main**":
sync_products()
