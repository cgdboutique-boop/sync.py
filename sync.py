import os
import json
import requests
import re

# -------------------------------
# CONFIG FROM ENVIRONMENT
# -------------------------------
SHOPIFY_STORE = os.environ["SHOPIFY_STORE"]  # e.g., cgdboutique.myshopify.com
SHOPIFY_TOKEN = os.environ["SHOPIFY_TOKEN"]
SUPPLIER_API_URL = os.environ["SUPPLIER_API_URL"]
SUPPLIER_TOKEN = os.environ["SUPPLIER_TOKEN"]

supplier_headers = {"X-Shopify-Access-Token": SUPPLIER_TOKEN, "Content-Type": "application/json"}
shopify_headers = {"X-Shopify-Access-Token": SHOPIFY_TOKEN, "Content-Type": "application/json"}

# -------------------------------
# HELPER FUNCTION TO CLEAN HTML
# -------------------------------
def clean_text(text):
    if not text:
        return ""
    # remove specific unwanted HTML tags
    text = re.sub(r"<\/?p>", "", text)
    text = re.sub(r"Â", "", text)
    text = re.sub(r"<\/?span.*?>", "", text)
    text = re.sub(r'data-mce-fragment="1"', "", text)
    return text.strip()

# -------------------------------
# FETCH SUPPLIER PRODUCTS
# -------------------------------
supplier_response = requests.get(SUPPLIER_API_URL, headers=supplier_headers)
if supplier_response.status_code != 200:
    print("❌ Supplier API request failed:", supplier_response.text)
    exit(1)

supplier_products = supplier_response.json().get("products", [])
print(f"ℹ️ Fetched {len(supplier_products)} products from supplier")

# -------------------------------
# SYNC TO SHOPIFY
# -------------------------------
for product in supplier_products:
    variants_payload = []
    for variant in product.get("variants", []):
        sku = variant.get("sku", "").strip()
        if not sku:
            # fallback: extract SKU from body_html if missing
            body = product.get("body_html", "")
            sku_match = re.search(r"#(\d+)", body)
            sku = sku_match.group(1) if sku_match else None
        if not sku:
            continue  # skip variant if no SKU found

        variants_payload.append({
            "option1": variant.get("option1", "").strip() or "Default",
            "sku": sku,
            "price": variant.get("price", "0.00"),
            "inventory_quantity": variant.get("inventory_quantity", 0),
            "inventory_management": "shopify",
            "inventory_policy": "deny"
        })

    # Clean product title/body
    title = clean_text(product.get("title", "No Title"))
    body_html = clean_text(product.get("body_html", ""))

    payload = {
        "product": {
            "title": title,
            "body_html": body_html,
            "vendor": product.get("vendor", "Supplier"),
            "product_type": product.get("product_type", ""),
            "tags": product.get("tags", ""),
            "variants": variants_payload,
            "images": [{"src": img.get("src")} for img in product.get("images", [])] if product.get("images") else [],
            "published": True
        }
    }

    # -------------------------------
    # CHECK IF PRODUCT EXISTS BY SKU
    # -------------------------------
    product_found = None
    for existing_page in range(1, 5):  # paginate up to 1000 products
        existing_url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products.json?limit=250&page={existing_page}"
        existing_resp = requests.get(existing_url, headers=shopify_headers)
        existing_products = existing_resp.json().get("products", [])
        if not existing_products:
            break
        for existing in existing_products:
            existing_skus = [v.get("sku") for v in existing.get("variants", [])]
            if any(v.get("sku") in existing_skus for v in variants_payload):
                product_found = existing
                break
        if product_found:
            break

    # -------------------------------
    # CREATE OR UPDATE
    # -------------------------------
    if product_found:
        product_id = product_found["id"]
        update_url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products/{product_id}.json"
        response = requests.put(update_url, headers=shopify_headers, data=json.dumps(payload))
        print(f"🔄 Updated product: {title} ({response.status_code})")
    else:
        create_url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products.json"
        response = requests.post(create_url, headers=shopify_headers, data=json.dumps(payload))
        print(f"🆕 Created product: {title} ({response.status_code})")

    # log response body for debugging
    try:
        print(json.dumps(response.json(), indent=2))
    except Exception:
        print("❌ Failed to parse Shopify response:", response.text)
