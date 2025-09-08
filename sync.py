import requests
import re

# Supplier API details
SUPPLIER_API_URL = "https://the-brave-ones-childrens-fashion.myshopify.com/admin/api/2023-10/products.json"
SUPPLIER_TOKEN = "YOUR_SUPPLIER_TOKEN"

# Your Shopify API details
SHOP_URL = "https://cgdboutique.myshopify.com/admin/api/2023-10/products.json"
SHOPIFY_TOKEN = "YOUR_SHOPIFY_TOKEN"

# Headers
supplier_headers = {"X-Shopify-Access-Token": SUPPLIER_TOKEN}
shopify_headers = {"X-Shopify-Access-Token": SHOPIFY_TOKEN, "Content-Type": "application/json"}

# Function to clean unwanted HTML/characters
def clean_text(text):
    if not text:
        return ""
    # Remove <p>, </p>, <span ...>, </span>, and Â
    text = re.sub(r"<\/?p>", "", text)
    text = re.sub(r"<span[^>]*>", "", text)
    text = re.sub(r"<\/span>", "", text)
    text = text.replace("Â", "")
    return text.strip()

# Fetch supplier products
supplier_response = requests.get(SUPPLIER_API_URL, headers=supplier_headers)
if supplier_response.status_code != 200:
    print("Failed to fetch supplier products:", supplier_response.text)
    exit(1)

supplier_products = supplier_response.json().get("products", [])

# Process each supplier product
for product in supplier_products:
    variants = []
    for variant in product.get("variants", []):
        variants.append({
            "option1": variant.get("option1", ""),
            "sku": variant.get("sku", ""),
            "inventory_quantity": variant.get("inventory_quantity", 0),
            "price": variant.get("price", "0.00"),
            "inventory_management": "shopify",
            "inventory_policy": "deny"
        })

    images = [{"src": img["src"]} for img in product.get("images", [])] if product.get("images") else []

    payload = {
        "product": {
            # Supplier body_html → Shopify title
            "title": clean_text(product.get("body_html", "No Title")),
            # Supplier title → Shopify description
            "body_html": clean_text(product.get("title", "")),
            "vendor": "",  # remove vendor
            "product_type": product.get("product_type", ""),
            "tags": ",".join(product.get("tags", [])) if isinstance(product.get("tags"), list) else product.get("tags", ""),
            "variants": variants,
            "images": images,
            "published": True
        }
    }

    # Collect SKUs for duplicate check
    supplier_skus = [v.get("sku", "") for v in product.get("variants", []) if v.get("sku")]

    existing = None
    for sku in supplier_skus:
        search_url = f"https://cgdboutique.myshopify.com/admin/api/2023-10/products.json?sku={sku}"
        check = requests.get(search_url, headers=shopify_headers)
        if check.status_code == 200 and check.json().get("products"):
            existing = check.json()["products"][0]  # found existing product
            break

    if existing:
        # Update existing product
        product_id = existing["id"]
        update_url = f"https://cgdboutique.myshopify.com/admin/api/2023-10/products/{product_id}.json"
        response = requests.put(update_url, headers=shopify_headers, json=payload)
        print(f"Updated product {product_id}: {response.status_code}")
    else:
        # Create new product
        response = requests.post(SHOP_URL, headers=shopify_headers, json=payload)
        print(f"Created new product: {response.status_code}")

    # ✅ Update inventory levels explicitly
    if "product" in response.json():
        shop_product = response.json()["product"]
        for idx, variant in enumerate(shop_product.get("variants", [])):
            if idx < len(product.get("variants", [])):
                supplier_variant = product["variants"][idx]
                inventory_item_id = variant.get("inventory_item_id")
                available = supplier_variant.get("inventory_quantity", 0)

                if inventory_item_id:
                    inv_url = "https://cgdboutique.myshopify.com/admin/api/2023-10/inventory_levels/set.json"
                    inv_payload = {
                        "location_id": YOUR_LOCATION_ID,  # replace with your store location ID
                        "inventory_item_id": inventory_item_id,
                        "available": available
                    }
                    inv_res = requests.post(inv_url, headers=shopify_headers, json=inv_payload)
                    print(f"Inventory updated for variant {variant.get('sku')}: {inv_res.status_code}")
