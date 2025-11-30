import os
import json
import requests

# Supplier credentials from environment
SUPPLIER_API_URL = os.environ["SUPPLIER_API_URL"]
SUPPLIER_TOKEN = os.environ["SUPPLIER_TOKEN"]

supplier_headers = {
    "X-Shopify-Access-Token": SUPPLIER_TOKEN,
    "Accept": "application/json"
}

def fetch_all_supplier_products(limit=250):
    products = []
    since_id = 0

    while True:
        params = {"limit": limit, "since_id": since_id}
        response = requests.get(SUPPLIER_API_URL, headers=supplier_headers, params=params)

        if response.status_code != 200:
            print("❌ Supplier API error:", response.text)
            break

        batch = response.json().get("products", [])
        if not batch:
            break

        products.extend(batch)
        since_id = max([p["id"] for p in batch])

    return products


if __name__ == "__main__":
    print("📥 Fetching all supplier products...")
    products = fetch_all_supplier_products()

    print(f"✅ Total products received: {len(products)}")

    # Save full JSON for inspection
    with open("supplier_raw.json", "w", encoding="utf-8") as f:
        json.dump(products, f, indent=2, ensure_ascii=False)

    print("📄 Saved full supplier JSON to supplier_raw.json")
    print("👉 Upload that file here so I can inspect entries like 10020036.")
