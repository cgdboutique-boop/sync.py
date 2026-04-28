#!/usr/bin/env python3

import os
import time
import json
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

def safe_title(text):
    text = clean(text)
    return text[:70] if text else "Untitled Product"

# ---------- Fetch ----------
def get_supplier_products():
    r = safe_request("GET", SUPPLIER_API_URL, headers=supplier_headers)
    if not r or r.status_code != 200:
        print("❌ Supplier fetch failed")
        return []
    return r.json().get("products", [])

# ---------- Build payload ----------
def build_payload(sp):
    supplier_id = sp.get("id")

    title = safe_title(sp.get("title"))
    desc = clean(sp.get("body_html"))

    # =========================================================
    # FIXED VARIANT LOGIC (THIS WAS BREAKING YOUR SYNC)
    # =========================================================

    first_variant = (sp.get("variants") or [{}])[0]

    sku = (first_variant.get("sku") or "").strip() or f"{supplier_id}"
    price = str(first_variant.get("price") or "0.00")

    variants = [
        {
            "option1": "Default Title",
            "price": price,
            "sku": sku
        }
    ]

    # images
    images = []
    for img in sp.get("images", []):
        if img.get("src"):
            images.append({"src": img["src"]})

    return {
        "product": {
            "title": title,
            "body_html": desc,
            "vendor": TARGET_VENDOR,
            "tags": f"supplier:{supplier_id}",
            "variants": variants,
            "images": images
        }
    }

# ---------- Create ----------
def create_product(payload):
    url = f"https://{SHOPIFY_STORE}/admin/api/{SHOPIFY_API_VERSION}/products.json"
    return safe_request("POST", url, headers=shopify_headers, json=payload)

# ---------- Main ----------
def sync():
    supplier = get_supplier_products()

    created = 0
    failed = 0

    print(f"🔄 Supplier products found: {len(supplier)}")

    for sp in supplier:
        sid = sp.get("id")
        if not sid:
            continue

        payload = build_payload(sp)

        print(f"🆕 Creating product {sid}")

        res = create_product(payload)

        if res and res.status_code in (200, 201):
            created += 1
        else:
            failed += 1
            print(f"❌ Create failed for {sid}")
            try:
                print("STATUS:", res.status_code)
                print("RESPONSE:", res.text)
            except:
                pass

    print("\n--- SYNC COMPLETE ---")
    print("Created:", created)
    print("Failed:", failed)

if __name__ == "__main__":
    sync()
