import os
import json
import requests

# Load supplier credentials
SUPPLIER_API_URL = os.environ["SUPPLIER_API_URL"]
SUPPLIER_TOKEN = os.environ["SUPPLIER_TOKEN"]

supplier_headers = {
    "X-Shopify-Access-Token": SUPPLIER_TOKEN,
    "Accept": "application/json"
}

def fetch_supplier_products(limit=250):
    products = []
    since_id = 0
    
    while True:
        params = {"limit": limit, "since_id": since_id}
        response = requests.get(SUPPLIER_API_URL, headers=supplier_headers, params=params)

        if response.status_code != 200:
            print(f"❌ Supplier API error: {response.text}")
            break

        batch = response.json().get("products", [])
        if not batch:
            break

        products.extend(batch)
        since_id = max([p["id"] for p in batch])

    return products


def test_supplier_skus():
    print("📥 Fetching all supplier products...")
    products = fetch_supplier_products()

    all_skus = []

    for p in products:
        for v in p.get("variants", []):
            sku = v.get("sku")
            all_skus.append(str(sku))

    # Remove None and empty
    clean_skus = sorted(set([s for s in all_skus if s and s != "None"]))

    print("\n📦 TOTAL SKUs FOUND:", len(clean_skus))

    # Print first 50 as preview
    print("\n🔍 PREVIEW OF SKUs:")
    for s in clean_skus[:50]:
        print(s)

    # Save full list
    with open("supplier_skus.txt", "w") as f:
        for s in clean_skus:
            f.write(s + "\n")

    print("\n✅ Full list saved to supplier_skus.txt")
    print("👉 Send me the file OR copy/paste examples here.")


if __name__ == "__main__":
    test_supplier_skus()
