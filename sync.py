import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()

# Supplier Shopify store
SUPPLIER_API_URL = "https://the-brave-ones-childrens-fashion.myshopify.com/admin/api/2023-10/products.json"
SUPPLIER_TOKEN = os.getenv("SUPPLIER_TOKEN")
supplier_headers = {"X-Shopify-Access-Token": SUPPLIER_TOKEN, "Content-Type": "application/json"}

# Your Shopify store
SHOP_URL = "https://cgdboutique.myshopify.com/admin/api/2023-10/products.json"
SHOPIFY_TOKEN = os.getenv("SHOPIFY_TOKEN")
shopify_headers = {"X-Shopify-Access-Token": SHOPIFY_TOKEN, "Content-Type": "application/json"}

# Helper: retry request
def safe_request(method, url, headers=None, json=None, retries=5, delay=1):
    for attempt in range(1, retries + 1):
        try:
            if method.upper() == "GET":
                r = requests.get(url, headers=headers, timeout=30)
            elif method.upper() == "POST":
                r = requests.post(url, headers=headers, json=json, timeout=30)
            elif method.upper() == "PUT":
                r = requests.put(url, headers=headers, json=json, timeout=30)
            else:
                raise ValueError("Unsupported method")
            
            if r.status_code in (200, 201):
                return r
            else:
                print(f"⚠️ Request failed ({r.status_code}): {r.text}. Attempt {attempt}/{retries}")
        except requests.exceptions.RequestException as e:
            print(f"⚠️ Request exception: {e}. Attempt {attempt}/{retries}")
        time.sleep(delay * attempt)
    raise Exception(f"Failed after {retries} retries: {url}")

# Fetch all supplier products (with pagination)
def fetch_supplier_products():
    products = []
    url = SUPPLIER_API_URL
    while url:
        r = safe_request("GET", url, headers=supplier_headers)
        data = r.json()
        products.extend(data.get("products", []))
        # Shopify pagination
        link = r.headers.get("Link")
        url = None
        if link and 'rel="next"' in link:
            url = link.split(";")[0].strip("<>")
    print(f"✅ Fetched {len(products)} supplier products")
    return products

# Fetch all Shopify products (by SKU)
def fetch_shopify_variants():
    variants_by_sku = {}
    url = SHOP_URL + "?limit=250"
    while url:
        r = safe_request("GET", url, headers=shopify_headers)
        data = r.json()
        for product in data.get("products", []):
            for variant in product.get("variants", []):
                sku = variant.get("sku")
                if sku:
                    variants_by_sku[sku] = variant
        # Pagination
        link = r.headers.get("Link")
        url = None
        if link and 'rel="next"' in link:
            url = link.split(";")[0].strip("<>")
    print(f"✅ Fetched {len(variants_by_sku)} Shopify variants by SKU")
    return variants_by_sku

# Create or update product in Shopify
def create_or_update_product(product, shopify_variants):
    sku_map = {v.get("sku"): v for v in shopify_variants.values() if v.get("sku")}
    variants_payload = []
    for variant in product.get("variants", []):
        variants_payload.append({
            "option1": variant.get("option1", ""),
            "sku": variant.get("sku", ""),
            "price": variant.get("price", "0.00"),
            "inventory_quantity": variant.get("inventory_quantity", 0)
        })

    images_payload = [{"src": img["src"]} for img in product.get("images", [])] if product.get("images") else []

    payload = {
        "product": {
            "title": product.get("title", "No Title"),
            "body_html": product.get("body_html", ""),
            "vendor": product.get("vendor", ""),
            "product_type": product.get("product_type", ""),
            "tags": ",".join(product.get("tags", [])) if isinstance(product.get("tags"), list) else product.get("tags", ""),
            "variants": variants_payload,
            "images": images_payload,
            "published": True
        }
    }

    # Check if first variant SKU exists
    first_sku = variants_payload[0].get("sku") if variants_payload else None
    existing_variant = sku_map.get(first_sku)

    if existing_variant:
        variant_id = existing_variant["id"]
        # Update price
        new_price = variants_payload[0]["price"]
        if str(existing_variant.get("price")) != str(new_price):
            r = safe_request("PUT", f"https://cgdboutique.myshopify.com/admin/api/2023-10/variants/{variant_id}.json",
                             headers=shopify_headers, json={"variant": {"id": variant_id, "price": new_price}})
            print(f"✅ Updated price for SKU {first_sku} to {new_price}")
        else:
            print(f"ℹ️ Price for SKU {first_sku} is already correct ({new_price})")
    else:
        r = safe_request("POST", SHOP_URL, headers=shopify_headers, json=payload)
        print(f"✅ Created new product: {product.get('title', 'No Title')} (SKU {first_sku})")

def main():
    shopify_variants = fetch_shopify_variants()
    supplier_products = fetch_supplier_products()

    for product in supplier_products:
        create_or_update_product(product, shopify_variants)

if __name__ == "__main__":
    main()
