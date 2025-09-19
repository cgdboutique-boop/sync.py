import os
import requests

# -------------------------------
# Environment variables
# -------------------------------
SHOPIFY_STORE = os.environ.get("SHOPIFY_STORE")
SHOPIFY_TOKEN = os.environ.get("SHOPIFY_TOKEN")
SUPPLIER_API_URL = os.environ.get("SUPPLIER_API_URL")
SUPPLIER_TOKEN = os.environ.get("SUPPLIER_TOKEN")
VENDOR_NAME = "CGD Kids Boutique"  # Your vendor name

# -------------------------------
# Helper functions
# -------------------------------
def fetch_supplier_products():
    headers = {
        "Authorization": f"Bearer {SUPPLIER_TOKEN}",
        "Content-Type": "application/json"
    }
    try:
        response = requests.get(SUPPLIER_API_URL, headers=headers, timeout=30)
        response.raise_for_status()
        products = response.json()
        print(f"Fetched {len(products)} supplier products")
        return products
    except requests.exceptions.HTTPError as e:
        print(f"Warning: Could not fetch supplier products ({e})")
        return []
    except Exception as e:
        print(f"Error fetching supplier products: {e}")
        return []

def get_shopify_products():
    url = f"https://{SHOPIFY_STORE}/admin/api/2025-01/products.json?limit=250"
    headers = {"X-Shopify-Access-Token": SHOPIFY_TOKEN}
    r = requests.get(url, headers=headers)
    r.raise_for_status()
    return r.json().get("products", [])

def delete_duplicates(products):
    seen_titles = {}
    duplicates = []
    headers = {"X-Shopify-Access-Token": SHOPIFY_TOKEN}

    for p in products:
        key = p['title'].lower()
        if key in seen_titles:
            duplicates.append(p)
        else:
            seen_titles[key] = p

    if duplicates:
        print(f"Found {len(duplicates)} duplicates. Deleting now...")
        for p in duplicates:
            del_url = f"https://{SHOPIFY_STORE}/admin/api/2025-01/products/{p['id']}.json"
            requests.delete(del_url, headers=headers)
            print(f"Deleted duplicate: {p['title']} (ID: {p['id']})")
    else:
        print("No duplicates found.")

def product_exists(shopify_products, title):
    title_lower = title.lower()
    return any(p['title'].lower() == title_lower for p in shopify_products)

def add_product_to_shopify(product):
    url = f"https://{SHOPIFY_STORE}/admin/api/2025-01/products.json"
    headers = {
        "X-Shopify-Access-Token": SHOPIFY_TOKEN,
        "Content-Type": "application/json"
    }

    payload = {
        "product": {
            "title": product["title"],
            "body_html": product.get("description", ""),
            "vendor": VENDOR_NAME,
            "variants": [
                {
                    "price": product.get("price", "0.00"),
                    "sku": product.get("sku", "")
                }
            ],
            "images": [{"src": img} for img in product.get("images", [])]
        }
    }

    r = requests.post(url, json=payload, headers=headers)
    if r.status_code == 201:
        print(f"Added product: {product['title']}")
    else:
        print(f"Failed to add product: {product['title']} ({r.status_code})")

# -------------------------------
# Main workflow
# -------------------------------
def main():
    try:
        print("Fetching Shopify products...")
        shopify_products = get_shopify_products()
    except Exception as e:
        print(f"Error fetching Shopify products: {e}")
        return

    delete_duplicates(shopify_products)

    supplier_products = fetch_supplier_products()
    if not supplier_products:
        print("Skipping product creation due to fetch error.")
        return

    print("Syncing supplier products to Shopify...")
    for sp in supplier_products:
        if not product_exists(shopify_products, sp["title"]):
            add_product_to_shopify(sp)
        else:
            print(f"Skipping duplicate product: {sp['title']}")

    print("Sync completed.")

if __name__ == "__main__":
    main()
