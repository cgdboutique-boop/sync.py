import os
import json
import requests
from time import sleep

# -------------------------------
# Load secrets from environment
# -------------------------------
SHOPIFY_STORE = os.environ["SHOPIFY_STORE"]
SHOPIFY_TOKEN = os.environ["SHOPIFY_TOKEN"]
SUPPLIER_API_URL = os.environ["SUPPLIER_API_URL"]
SUPPLIER_TOKEN = os.environ["SUPPLIER_TOKEN"]

# -------------------------------
# Headers
# -------------------------------
supplier_headers = {
    "X-Shopify-Access-Token": SUPPLIER_TOKEN,
    "Accept": "application/json"
}
shopify_headers = {
    "X-Shopify-Access-Token": SHOPIFY_TOKEN,
    "Content-Type": "application/json"
}

# -------------------------------
# Helper functions
# -------------------------------
def fetch_supplier_products(limit=250):
    """Fetch all supplier products using pagination"""
    products = []
    page = 1
    while True:
        params = {"limit": limit, "page": page}
        response = requests.get(SUPPLIER_API_URL, headers=supplier_headers, params=params)
        if response.status_code != 200:
            print(f"❌ Supplier API error (page {page}): {response.text}")
            break
        data = response.json().get("products", [])
        if not data:
            break
        products.extend(data)
        print(f"📥 Fetched {len(data)} products from supplier (page {page})")
        page += 1
        sleep(0.2)  # slight delay to avoid rate limiting
    print(f"✅ Total supplier products fetched: {len(products)}")
    return products

def check_shopify_product(handle):
    """Check if product exists in Shopify by handle"""
    url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products.json?handle={handle}"
    resp = requests.get(url, headers=shopify_headers)
    if resp.status_code != 200:
        print(f"❌ Shopify check error: {resp.text}")
        return None
    products = resp.json().get("products", [])
    return products[0] if products else None

def clean_text(text):
    """Remove unwanted HTML and whitespace"""
    if not text:
        return ""
    return text.replace("<p>", "").replace("</p>", "").replace("Â", "").replace("<span data-mce-fragment=\"1\">", "").replace("</span>", "").strip()

# -------------------------------
# Main Sync
# -------------------------------
supplier_products = fetch_supplier_products()

for product in supplier_products:
    title = clean_text(product.get("title") or product.get("body_html") or "No Title")
    body_html = clean_text(product.get("body_html") or product.get("title") or "")
    vendor = product.get("vendor") or "Supplier"
    product_type = product.get("product_type") or ""
    tags = product.get("tags") or ""
    handle = product.get("handle") or title.replace(" ", "-").lower()

    # Variants
    variants = []
    for v in product.get("variants", []):
        sku = v.get("sku")
        if not sku:
            # extract SKU from title/body if none
            if "#" in title:
                sku = title.split("#")[1].split()[0].strip()
            else:
                sku = f"NO-SKU-{v.get('id','0')}"
        variants.append({
            "option1": v.get("option1","").strip(),
            "sku": sku.strip(),
            "price": v.get("price","0.00"),
            "inventory_quantity": v.get("inventory_quantity", 0),
            "inventory_management": "shopify",
            "inventory_policy": "deny"
        })

    payload = {
        "product": {
            "title": title,
            "body_html": body_html,
            "vendor": vendor,
            "product_type": product_type,
            "tags": tags,
            "handle": handle,
            "variants": variants,
            "published": True
        }
    }

    # Check if product exists
    existing_product = check_shopify_product(handle)
    if existing_product:
        product_id = existing_product["id"]
        url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products/{product_id}.json"
        resp = requests.put(url, headers=shopify_headers, data=json.dumps(payload))
        action = "Updated"
    else:
        url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products.json"
        resp = requests.post(url, headers=shopify_headers, data=json.dumps(payload))
        action = "Created"

    try:
        resp_json = resp.json()
        print(f"✅ {action} product: {title} (handle: {handle})")
    except Exception:
        print(f"❌ {action} failed: {resp.text}")
