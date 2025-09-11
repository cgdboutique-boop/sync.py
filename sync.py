import requests
import time

SUPPLIER_API_URL = "https://the-brave-ones-childrens-fashion.myshopify.com/admin/api/2025-07/products.json"
SUPPLIER_TOKEN = "your_supplier_token_here"

supplier_headers = {
    "X-Shopify-Access-Token": SUPPLIER_TOKEN,
    "Content-Type": "application/json"
}

def fetch_supplier_products(batch_size=100):
    all_products = []
    page_info = None
    attempt = 1

    while True:
        try:
            url = SUPPLIER_API_URL
            if page_info:
                url += f"&page_info={page_info}&limit={batch_size}"
            else:
                url += f"?limit={batch_size}"

            print(f"Fetching supplier batch (Attempt {attempt})...")
            response = requests.get(url, headers=supplier_headers, timeout=30)  # <- timeout added
            response.raise_for_status()
            
            data = response.json()
            products = data.get("products", [])
            if not products:
                print("No more products returned from supplier.")
                break

            all_products.extend(products)
            print(f"Fetched {len(products)} products this batch")
            
            # Pagination (if needed)
            page_info = data.get("next_page_info")  # adapt if supplier supports pagination
            if not page_info:
                break

            time.sleep(2)  # small delay between batches
            attempt = 1  # reset attempt counter
        except Exception as e:
            print(f"Attempt {attempt} failed: {e}")
            attempt += 1
            if attempt > 3:
                print("Failed 3 times. Exiting fetch loop.")
                break
            time.sleep(5)

    return all_products

supplier_products = fetch_supplier_products()
print(f"Total supplier products fetched: {len(supplier_products)}")
