#!/usr/bin/env python3

import os
import requests
import json

SUPPLIER_API_URL = os.environ.get("SUPPLIER_API_URL")
SUPPLIER_TOKEN = os.environ.get("SUPPLIER_TOKEN")

if not SUPPLIER_API_URL or not SUPPLIER_TOKEN:
    raise SystemExit("Missing supplier env vars")

headers = {
    "X-Shopify-Access-Token": SUPPLIER_TOKEN,
    "Accept": "application/json"
}

print("\n🔎 CALLING SUPPLIER API...\n")
r = requests.get(SUPPLIER_API_URL, headers=headers)

print("STATUS CODE:", r.status_code)

print("\n--- RESPONSE HEADERS ---")
for k, v in r.headers.items():
    print(k, ":", v)

print("\n--- RESPONSE BODY KEYS ---")
try:
    data = r.json()
    print(data.keys())
except Exception as e:
    print("Not JSON response:", e)

print("\n--- SAMPLE PRODUCTS (if any) ---")
try:
    products = data.get("products", [])
    print("Total returned in THIS request:", len(products))
    print("First product example:")
    if products:
        print(json.dumps(products[0], indent=2)[:2000])
except Exception as e:
    print("Error reading products:", e)

print("\n--- LOOKING FOR PAGINATION CLUES ---")

# common pagination patterns
keys_to_check = [
    "next", "next_page", "next_page_url",
    "cursor", "page", "page_info", "offset",
    "links", "link"
]

for k in keys_to_check:
    if isinstance(data, dict) and k in data:
        print(f"FOUND: {k} ->", data[k])

print("\n🔚 DONE")
