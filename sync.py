#!/usr/bin/env python3

import os
import time
import re
import requests

# ---------- CONFIG ----------
SHOPIFY_API_VERSION = os.environ.get("SHOPIFY_API_VERSION", "2025-07")
TARGET_VENDOR = "CGD Kids Boutique"
RATE_LIMIT_SLEEP = 0.5

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

# ---------- REQUEST ----------
def safe_request(method, url, **kwargs):
    for _ in range(3):
        try:
            r = requests.request(method, url, timeout=60, **kwargs)
            time.sleep(RATE_LIMIT_SLEEP)
            return r
        except Exception:
            time.sleep(2)
    return None

# ---------- CLEAN ----------
def clean(text):
    text = re.sub(r'<[^>]+>', '', text or '')
    return re.sub(r'\s+', ' ', text).strip()

# ---------- SUPPLIER ----------
def get_supplier_products():
    products = []
    url = SUPPLIER_API_URL
    seen = set()

    while url:
        if url in seen:
            break

        seen.add(url)

        r = safe_request("GET", url, headers=supplier_headers)
        if not r or r.status_code != 200:
            break

        data = r.json()
        products.extend(data.get("products", []))

        link = r.headers.get("Link")
        next_url = None

        if link and 'rel="next"' in link:
            for part in link.split(","):
                if 'rel="next"' in part:
                    next_url = part.split(";")[0].strip("<> ")
                    break

        url = next_url

    return products

# ---------- SHOPIFY ----------
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
        since_id = max(p["id"] for p in batch)

    return products

# ---------- INDEX ----------
def build_index(products):
    idx = {"sku": {}, "tag": {}}

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

# ---------- PAYLOAD ----------
def build_payload(sp):
    supplier_id = sp.get("id")
    tag = f"supplier:{supplier_id}"

    title = clean(sp.get("title") or "")[:120]
    desc = clean(sp.get("body_html") or "")

    supplier_tags = sp.get("tags", "")
    combined_tags = f"{supplier_tags}, {tag}" if supplier_tags else tag

    variants = []

    for i, v in enumerate(sp.get("variants", [])):
        sku = (v.get("sku") or "").strip() or f"{supplier_id}-{i+1}"
        qty = v.get("inventory_quantity", 0)

        variants.append({
            "option1": v.get("title") or "Default Title",
            "sku": sku,
            "price": str(v.get("price") or "0.00"),

            # 🔥 IMPORTANT CHANGE HERE
            "inventory_management": "shopify",

            # ❌ OLD: continue selling when out of stock
            # "inventory_policy": "continue",

            # ✅ NEW: DO NOT allow selling when stock is 0
            "inventory_policy": "deny",

            "inventory_quantity": qty
        })

    images = []
    if sp.get("images"):
        for img in sp["images"]:
            if img.get("src"):
                images.append({"src": img["src"]})

    return {
        "product": {
            "title": title,
            "body_html": desc,
            "vendor": TARGET_VENDOR,
            "tags": combined_tags,
            "variants": variants,
            "images": images
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

    created = updated = 0

    print(f"\n🔄 Supplier products: {len(supplier)}\n")

    for sp in supplier:
        sid = sp.get("id")
        if not sid:
            continue

        tag = f"supplier:{sid}"
        payload = build_payload(sp)

        found = None

        # SKU match first
        for v in sp.get("variants", []):
            sku = (v.get("sku") or "").strip()
            if sku and sku in idx["sku"]:
                found = idx["sku"][sku]
                break

        # tag fallback
        if not found:
            found = idx["tag"].get(tag)

        if found:
            res = update_product(found["id"], payload)
            if res and res.status_code in (200, 201):
                updated += 1
        else:
            print(f"🆕 Creating {sid}")
            res = create_product(payload)
            if res and res.status_code in (200, 201):
                created += 1

    print("\n--- SYNC COMPLETE ---")
    print("Created:", created)
    print("Updated:", updated)

# ---------- RUN ----------
if __name__ == "__main__":
    sync()
