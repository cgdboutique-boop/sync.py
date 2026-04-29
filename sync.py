#!/usr/bin/env python3

import os
import time
import re
import requests

# ---------- Config ----------
SHOPIFY_API_VERSION = os.environ.get("SHOPIFY_API_VERSION", "2025-07")
TARGET_VENDOR = "CGD Kids Boutique"
RATE_LIMIT_SLEEP = 0.6

SHOPIFY_STORE = os.environ.get("SHOPIFY_STORE")
SHOPIFY_TOKEN = os.environ.get("SHOPIFY_TOKEN")
SUPPLIER_API_URL = os.environ.get("SUPPLIER_API_URL")
SUPPLIER_TOKEN = os.environ.get("SUPPLIER_TOKEN")

for name in ("SHOPIFY_STORE", "SHOPIFY_TOKEN", "SUPPLIER_API_URL", "SUPPLIER_TOKEN"):
    if not globals().get(name):
        raise SystemExit(f"Missing env var: {name}")

shopify_headers = {
    "X-Shopify-Access-Token": SHOPIFY_TOKEN,
    "Content-Type": "application/json"
}

supplier_headers = {
    "X-Shopify-Access-Token": SUPPLIER_TOKEN,
    "Accept": "application/json"
}

# ---------- Helpers ----------
def safe_request(method, url, **kwargs):
    for _ in range(3):
        try:
            r = requests.request(method, url, timeout=60, **kwargs)
            time.sleep(RATE_LIMIT_SLEEP)
            return r
        except Exception:
            time.sleep(2)
    return None

def clean(text):
    text = re.sub(r'<[^>]+>', '', text or '')
    return re.sub(r'\s+', ' ', text).strip()

# ---------- SUPPLIER (FIXED PAGINATION) ----------
def get_supplier_products():
    products = []
    url = SUPPLIER_API_URL

    while url:
        r = safe_request("GET", url, headers=supplier_headers)

        if not r or r.status_code != 200:
            print("❌ Supplier fetch failed")
            break

        data = r.json()
        products.extend(data.get("products", []))

        # Shopify-style pagination via Link header
        link = r.headers.get("Link")
        url = None

        if link and 'rel="next"' in link:
            next_part = link.split(";")[0]
            url = next_part.strip("<> ")

    return products

# ---------- SHOPIFY FETCH ----------
def get_all_shopify_products():
    products = []
    since_id = 0

    while True:
        url = f"https://{SHOPIFY_STORE}/admin/api/{SHOPIFY_API_VERSION}/products.json"
        params = {"limit": 250, "since_id": since_id}
        r = safe_request("GET", url, headers=shopify_headers, params=params)

        if not r or r.status_code != 200:
            break

        batch = r.json().get("products", [])
        if not batch:
            break

        products.extend(batch)
        since_id = max([p["id"] for p in batch])

    return products

# ---------- INDEX ----------
def build_index(products):
    idx = {"tag": {}, "sku": {}}

    for p in products:
        for t in (p.get("tags") or "").split(","):
            t = t.strip()
            if t.startswith("supplier:"):
                idx["tag"][t] = p

        for v in p.get("variants", []):
            sku = (v.get("sku") or "").strip()
            if sku:
                idx["sku"][sku] = p

    return idx

# ---------- SAFETY CHECK ----------
def check_shopify_by_tag(tag):
    url = f"https://{SHOPIFY_STORE}/admin/api/{SHOPIFY_API_VERSION}/products.json"
    params = {"limit": 250, "fields": "id,tags"}
    r = safe_request("GET", url, headers=shopify_headers, params=params)

    if not r or r.status_code != 200:
        return None

    for p in r.json().get("products", []):
        if tag in (p.get("tags") or ""):
            return p

    return None

# ---------- BUILD PAYLOAD ----------
def build_payload(sp):
    supplier_id = sp.get("id")
    tag = f"supplier:{supplier_id}"

    title = clean(sp.get("title") or "")[:70]
    desc = clean(sp.get("body_html") or "")

    first_variant = (sp.get("variants") or [{}])[0]

    sku = (first_variant.get("sku") or "").strip() or str(supplier_id)

    try:
        price = str(float(first_variant.get("price") or 0))
    except:
        price = "0.00"

    variants = [{
        "option1": "Default Title",
        "price": price,
        "sku": sku
    }]

    return {
        "product": {
            "title": title,
            "body_html": desc,
            "vendor": TARGET_VENDOR,
            "tags": tag,
            "variants": variants
        }
    }

# ---------- CREATE / UPDATE ----------
def create_product(payload):
    url = f"https://{SHOPIFY_STORE}/admin/api/{SHOPIFY_API_VERSION}/products.json"
    return safe_request("POST", url, headers=shopify_headers, json=payload)

def update_product(pid, payload):
    url = f"https://{SHOPIFY_STORE}/admin/api/{SHOPIFY_API_VERSION}/products/{pid}.json"
    return safe_request("PUT", url, headers=shopify_headers, json=payload)

# ---------- MAIN ----------
def sync():
    supplier = get_supplier_products()
    shopify = get_all_shopify_products()
    idx = build_index(shopify)

    created = updated = skipped = 0

    print(f"\n🔄 Supplier products found: {len(supplier)}\n")

    for sp in supplier:
        sid = sp.get("id")
        if not sid:
            skipped += 1
            continue

        tag = f"supplier:{sid}"
        payload = build_payload(sp)

        found = idx["tag"].get(tag)

        if not found:
            for v in sp.get("variants", []):
                sku = (v.get("sku") or "").strip()
                if sku and sku in idx["sku"]:
                    found = idx["sku"][sku]
                    break

        if not found:
            found = check_shopify_by_tag(tag)

        if found:
            res = update_product(found["id"], payload)
            if res and res.status_code in (200, 201):
                updated += 1
        else:
            print(f"🆕 Creating product {sid}")
            res = create_product(payload)

            if res and res.status_code in (200, 201):
                created += 1
                newp = res.json().get("product")
                if newp:
                    shopify.append(newp)
                    idx = build_index(shopify)
            else:
                print(f"❌ Create failed for {sid}")
                if res:
                    print("STATUS:", res.status_code)
                    print("RESPONSE:", res.text)

    print("\n--- SYNC COMPLETE ---")
    print(f"Created: {created}")
    print(f"Updated: {updated}")
    print(f"Skipped: {skipped}")

# ---------- RUN ----------
if __name__ == "__main__":
    sync()
