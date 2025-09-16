import os
import json
import requests

# -----------------------------
# Load secrets from environment
# -----------------------------
SHOPIFY_STORE = os.environ.get("SHOPIFY_STORE")  # e.g., cgdboutique.myshopify.com
SHOPIFY_TOKEN = os.environ.get("SHOPIFY_TOKEN")
SUPPLIER_API_URL = os.environ.get("SUPPLIER_API_URL")
SUPPLIER_TOKEN = os.environ.get("SUPPLIER_TOKEN")

# -----------------------------
# Helper function
# -----------------------------
def safe_str(text):
    """Convert None to empty string and strip"""
    if text is None:
        return ""
    return str(text).strip()

# -----------------------------
# Headers
# -----------------------------
supplier_headers = {
    "X-Shopify-Access-Token": SUPPLIER_TOKEN,
    "Accept": "application/json"
}
shopify_headers = {
    "X-Shopify-Access-Token": SHOPIFY_TOKEN,
    "Content-Type": "application/json"
}

# -----------------------------
# Fetch supplier products
# -----------------------------
supplier_response = requests.get(SUPPLIER_API_URL, headers=supplier_headers)
if supplier_response.status_code != 200:
    print(f"❌ Failed to fetch supplier products: {supplier_response.text}")
    exit(1)

supplier_data = supplier_response.json()
products = supplier_data.get("products", [])

# -----------------------------
# Sync products
# -----------------------------
for product in products:
    title = safe_str(product.get("title"))
    body_html = safe_str(product.get("body_html"))
    vendor = safe_str(product.get("vendor"))
    product_type = safe_str(product.get("product_type"))
    tags = safe_str(product.get("tags"))
    
    # Use SKU of first variant or generate handle from title
    variants = product.get("variants", [])
    if not variants:
        print(f"⚠️ Product '{title}' has no variants. Skipping.")
        continue

    first_variant = variants[0]
    base_sku = safe_str(first_variant.get("sku")).replace("#", "")
    handle = base_sku if base_sku else title.lower().replace(" ", "-")

    # Clean variants
    clean_variants = []
    for v in variants:
        clean_variants.append({
            "option1": safe_str(v.get("option1")),
            "sku": safe_str(v.get("sku")),
            "price": safe_str(v.get("price")),
            "inventory_quantity": v.get("inventory_quantity", 0),
            "inventory_management": "shopify",
            "inventory_policy": "deny"
        })

    # Clean images
    images = [{"src": img.get("src")} for img in product.get("images", []) if img.get("src")]

    payload = {
        "product": {
            "title": title,
            "body_html": body_html,
            "vendor": vendor,
            "product_type": product_type,
            "handle": handle,
            "tags": tags,
            "variants": clean_variants,
            "images": images,
            "published": True
        }
    }

    # -----------------------------
    # Check if product exists
    # -----------------------------
    check_url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products.json?handle={handle}"
    check_response = requests.get(check_url, headers=shopify_headers)
    existing = check_response.json().get("products", [])

    if existing:
        # Update existing product
        product_id = existing[0]["id"]
        update_url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products/{product_id}.json"
        response = requests.put(update_url, headers=shopify_headers, data=json.dumps(payload))
        action = "Updated"
    else:
        # Create new product
        create_url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products.json"
        response = requests.post(create_url, headers=shopify_headers, data=json.dumps(payload))
        action = "Created"

    # -----------------------------
    # Log result
    # -----------------------------
    if response.status_code in [200, 201]:
        print(f"✅ {action} product: {title} (handle: {handle})")
    else:
        print(f"❌ Failed to {action.lower()} product: {title}")
        try:
            print(json.dumps(response.json(), indent=2))
        except Exception:
            print(response.text)
