import os
import json
import requests

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

# --- Fetch supplier products ---

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

# --- Get existing Shopify product by handle ---

def get_shopify_product_by_handle(handle):
url = f"https://{SHOPIFY_STORE}.myshopify.com/admin/api/2025-07/products.json?handle={handle}"
response = requests.get(url, headers=shopify_headers)
if response.status_code == 200:
products = response.json().get("products", [])
if products:
return products[0]
return None

# --- Update a single variant ---

def update_variant(variant_id, variant_data):
url = f"https://{SHOPIFY_STORE}.myshopify.com/admin/api/2025-07/variants/{variant_id}.json"
payload = {"variant": variant_data}
response = requests.put(url, headers=shopify_headers, json=payload)
return response.status_code in (200, 201)

# --- Sync a single product ---

def sync_product_to_shopify(product):
if not product.get("variants"):
print(f"⚠ Skipping {product.get('title', 'Unnamed Product')} - no variants")
return

```
handle = product.get("handle") or product.get("title", "product").lower().replace(" ", "-")
existing_product = get_shopify_product_by_handle(handle)

if existing_product:
    product_id = existing_product["id"]
    print(f"🔄 Updating product: {product.get('title')}")
    # Update product info (title, vendor, tags, body)
    product_payload = {
        "product": {
            "id": product_id,
            "title": product.get("title", "Unnamed Product"),
            "body_html": product.get("body_html", ""),
            "vendor": product.get("vendor", "Default Vendor"),
            "tags": product.get("tags", "")
        }
    }
    url = f"https://{SHOPIFY_STORE}.myshopify.com/admin/api/2025-07/products/{product_id}.json"
    response = requests.put(url, headers=shopify_headers, json=product_payload)
    if response.status_code not in (200, 201):
        print(f"❌ Failed to update product {product.get('title')}: {response.text}")
        return

    # Update each variant individually
    for v in product["variants"]:
        # Try to find matching variant by option1 in Shopify
        matching_variant = next((mv for mv in existing_product["variants"] if mv["option1"] == v.get("option1")), None)
        variant_data = {
            "price": v.get("price", "0.00"),
            "inventory_quantity": v.get("inventory_quantity", 0),
            "sku": v.get("sku", ""),
            "requires_shipping": v.get("requires_shipping", True)
        }
        if matching_variant:
            success = update_variant(matching_variant["id"], variant_data)
            if success:
                print(f"✅ Updated variant {v.get('option1')}")
            else:
                print(f"❌ Failed variant {v.get('option1')}")
        else:
            # Add new variant if not exists
            url_add = f"https://{SHOPIFY_STORE}.myshopify.com/admin/api/2025-07/products/{product_id}/variants.json"
            payload_add = {"variant": {"option1": v.get("option1", "Default"), **variant_data}}
            response_add = requests.post(url_add, headers=shopify_headers, json=payload_add)
            if response_add.status_code in (200, 201):
                print(f"✅ Created new variant {v.get('option1')}")
            else:
                print(f"❌ Failed to create variant {v.get('option1')}: {response_add.text}")

else:
    # Create new product with all variants
    handle_safe = handle
    payload = {
        "product": {
            "title": product.get("title", "Unnamed Product"),
            "body_html": product.get("body_html", ""),
            "vendor": product.get("vendor", "Default Vendor"),
            "handle": handle_safe,
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
    url_create = f"https://{SHOPIFY_STORE}.myshopify.com/admin/api/2025-07/products.json"
    response_create = requests.post(url_create, headers=shopify_headers, json=payload)
    if response_create.status_code in (200, 201):
        print(f"✅ Created product: {product.get('title')}")
    else:
        print(f"❌ Failed to create product {product.get('title')}: {response_create.text}")
```

# --- Main ---

if **name** == "**main**":
print("📥 Fetching all supplier products...")
products = fetch_all_supplier_products()
print(f"✅ Total products received: {len(products)}")

```
# Save raw JSON
with open("supplier_raw.json", "w", encoding="utf-8") as f:
    json.dump(products, f, indent=2, ensure_ascii=False)
print("📄 Saved full supplier JSON to supplier_raw.json")

print("🔄 Starting Shopify sync...")
for product in products:
    sync_product_to_shopify(product)

print("✅ Shopify sync complete!")
```
