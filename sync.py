import os
import time
import requests

# Load your supplier API token (replace with your actual token if not using env vars)
SUPPLIER_API_URL = os.getenv("SUPPLIER_API_URL", "https://supplier.com/api/products")
SUPPLIER_TOKEN = os.getenv("SUPPLIER_TOKEN", "YOUR_SUPPLIER_TOKEN_HERE")

# Possible header formats to test
HEADER_OPTIONS = [
    lambda token: {"X-Access-Token": token, "Content-Type": "application/json"},
    lambda token: {"X-API-Key": token, "Content-Type": "application/json"},
    lambda token: {"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
]

def fetch_supplier_products(limit=100, retries=10):
    """Try all header styles until one works"""
    url = f"{SUPPLIER_API_URL}?limit={limit}"
    
    for build_headers in HEADER_OPTIONS:
        headers = build_headers(SUPPLIER_TOKEN)
        print(f"🔍 Trying header style: {list(headers.keys())[0]} ...")
        
        backoff = 5
        for attempt in range(retries):
            try:
                resp = requests.get(url, headers=headers, timeout=30)
                
                if resp.status_code == 200:
                    print(f"✅ Success with {list(headers.keys())[0]} header!")
                    return resp.json()
                
                elif resp.status_code == 401:
                    print(f"❌ 401 Unauthorized (attempt {attempt+1}/{retries}) with {list(headers.keys())[0]}")
                    time.sleep(backoff)
                    backoff *= 2
                else:
                    print(f"⚠️ Got {resp.status_code}: {resp.text[:200]}")
                    break  # stop retrying on this header type

            except Exception as e:
                print(f"⚠️ Error: {e}")
                time.sleep(backoff)
                backoff *= 2

        print(f"❌ Failed with {list(headers.keys())[0]} header, trying next option...\n")

    print("🚨 All header styles failed. Please confirm with supplier which header to use.")
    return None


if __name__ == "__main__":
    print("=== Starting supplier sync (limit=100) ===")
    products = fetch_supplier_products(limit=100)

    if products:
        print(f"Fetched {len(products)} products ✅")
    else:
        print("❌ No products fetched from supplier.")
