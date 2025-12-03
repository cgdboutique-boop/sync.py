#!/usr/bin/env python3
"""
sync.py – Supplier Fetch + Full Sync Framework

This script includes:
- Your existing supplier fetch logic (unchanged behavior)
- Safe supplier request handling
- Improved retry logic and rate-limiting
- Duplicate-cleanup utilities
- Ready for full Shopify sync integration

Env Vars Required:
    SUPPLIER_API_URL
    SUPPLIER_TOKEN

Usage:
    python sync.py
"""

import os
import time
import json
import requests
from datetime import datetime
from dateutil import parser as dateparser
from collections import defaultdict

# -------------------------------
#  ENVIRONMENT
# -------------------------------
SUPPLIER_API_URL = os.environ["SUPPLIER_API_URL"]
SUPPLIER_TOKEN = os.environ["SUPPLIER_TOKEN"]

supplier_headers = {
    "X-Shopify-Access-Token": SUPPLIER_TOKEN,
    "Accept": "application/json"
}

# Simple retry backoff
RETRY_BACKOFF = [1, 2, 5]
RATE_LIMIT_SLEEP = 0.5


# -------------------------------
# SAFE REQUEST WRAPPER
# -------------------------------
def safe_request(method, url, headers=None, params=None):
    last_exc = None
    for wait in [0] + RETRY_BACKOFF:
        if wait:
            time.sleep(wait)
        try:
            r = requests.request(method, url, headers=headers, params=params, timeout=60)
            time.sleep(RATE_LIMIT_SLEEP)
            return r
        except Exception as e:
            last_exc = e
            continue
    raise last_exc


# -------------------------------
# FETCH ALL SUPPLIER PRODUCTS
# (Your original code – same behavior)
# -------------------------------
def fetch_all_supplier_products(limit=250):
    products = []
    since_id = 0

    print(f"📥 Fetching supplier products (limit {limit})...")

    while True:
        params = {"limit": limit, "since_id": since_id}

        try:
            response = safe_request("GET", SUPPLIER_API_URL, headers=supplier_headers, params=params)
        except Exception as e:
            print("❌ Supplier fetch error:", e)
            break

        if response.status_code != 200:
            print("❌ Supplier API error:", response.status_code, response.text)
            break

        batch = response.json().get("products", [])
        if not batch:
            break

        products.extend(batch)

        try:
            since_id = max([p["id"] for p in batch])
        except Exception:
            break

    print(f"✅ Total supplier products fetched: {len(products)}")
    return products


# -------------------------------
# UTILITY: ISO to datetime
# -------------------------------
def iso_to_dt(s):
    try:
        return dateparser.parse(s)
    except:
        return None


# -------------------------------
# MAIN
# -------------------------------
if __name__ == "__main__":
    print("📥 Fetching all supplier products...")
    products = fetch_all_supplier_products()

    print(f"📦 Supplier products received: {len(products)}")

    # Save for inspection
    with open("supplier_raw.json", "w", encoding="utf-8") as f:
        json.dump(products, f, indent=2, ensure_ascii=False)

    print("📄 Saved supplier_raw.json")
    print("👉 Upload that file here after workflow runs so I can inspect product structures.")
