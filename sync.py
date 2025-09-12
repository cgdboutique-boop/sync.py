import os
import requests
import time

# -------------------------------
# CONFIG (from GitHub secrets)
# -------------------------------
SHOPIFY_STORE = os.environ.get("SHOPIFY_STORE")
SHOPIFY_TOKEN = os.environ.get("SHOPIFY_TOKEN")
SUPPLIER_API_URL = os.environ.get("SUPPLIER_API_URL")
SUPPLIER_TOKEN = os.environ.get("SUPPLIER_TOKEN")

if not SHOPIFY_STORE or not SHOPIFY_TOKEN:
    raise ValueError("SHOPIFY_STORE or SHOPIFY_TOKEN is not set!")
if not SUPPLIER_API_URL or not SUPPLIER_TOKEN:
    raise ValueError("SUPPLIER_API_URL or SUPPLIER_TOKEN is not set!")

SHOP_URL = f"https://{SHOPIFY_STORE}.myshopify.com/admin/api/2025-07"
shopify_headers = {
    "X-Shopify-Access-Token": SHOPIFY_TOKEN,
    "Content-Type": "application/json"
}
supplier_headers = {
    "Authorization": f"Bearer {SUPPLIER_TOKEN}",
    "Content-Type": "application/json"
}

# -------------------------------
# HELPER FUNCTION
# -------------------------------
def request_with_retry(method, url, headers=None, json=None, max_retries=5):
    retry_delay = 2
    for attempt in range(max_retries):
        try:
            response = requests.request(method, url, headers=headers, json=json)
            if response.status_code in [401, 429]:
                wait = int(response.headers.get("Retry-After", retry_delay))
                print(f"{response.status_code} error. Retrying in {wait}s...")
                time.sleep(wait)
                retry_delay *= 2
                continue
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            print(f"Request error: {e}. Retrying in {retry_delay}s...")
            time.sleep(retry_delay)
            retry_delay *= 2
    return None

# -------------------------------
# FETCH SUPPLIER PRODUCTS (batch)
# -------------------------------
def fetch_supplier_products(limit=100):
    url = f"{SUPPLIER_API_URL}?limit={limit}"
    r = request_with_retry("GET", url, headers=supplier_headers)
    if r is None:
        print("❌ Failed to fetch supplier products.")
        return []
    return r.json().get("products", [])

# -------------------------------
# FETCH SHOPIFY PRODUCTS (batch)
# -------------------------------
def fetch_shopify_products(limit=100):
    url = f"{SHOP_URL}/products.json?limit={limit}"
    r = request_with_retry("GET", url, headers=shopify_headers)
    if r is None:
        print("❌ Failed to fetch Shopify products.")
        return []
    return r.json().get("products", [])

# -------------------------------
# MATCH PRODUCT (SKU > Handle > Title/Desc)
# -------------------------------
def match_product(sp, shopify_products):
    sp_sku = None
    if sp.get("variants"):
        sp_sku = sp["variants"][0].get("sku")

    sp_handle = sp.get("handle", "")
    sp_title = sp.get("title", "").lower()
    sp_body = (sp.get("body_html", "") or "").lower()

    for p in shopify_products:
        # 1. Match SKU
        for v in p.get("variants", []):
            if sp_sku and v.get("sku") == sp_sku:
                return p
        # 2. Match handle
        if sp_handle and p.get("handle") == sp_handle:
            return p
        # 3. Match by title/body (loose check)
        if sp_title and sp_title in p.get("title", "").lower():
            return p
        if sp_body and sp_body[:40] in (p.get("body_html", "") or "").lower():
            return p
    return None

# -------------------------------
# SYNC SUPPLIER PRODUCT
# -------------------------------
def sync_product(sp, shopify_products):
    existing = match_product(sp, shopify_products)

    handle = sp.get("handle", f"sku-{sp.get('variants',[{}])[0].get('sku','no-handle
