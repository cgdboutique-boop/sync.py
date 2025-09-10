# debug_sync.py
import os
import requests
import sys
from itertools import islice

SUPPLIER_API = "https://the-brave-ones-childrens-fashion.myshopify.com/admin/api/2023-10/products.json"
SHOP_API_BASE = "https://cgdboutique.myshopify.com/admin/api/2023-10"

SUPPLIER_TOKEN = os.getenv("SUPPLIER_TOKEN")
SHOPIFY_TOKEN = os.getenv("SHOPIFY_TOKEN")
DRY_RUN = os.getenv("DRY_RUN", "true").lower() != "false"  # default True

def mask(s):
    if not s:
        return "(missing)"
    return s[:4] + "…" + s[-4:]

print("ENV CHECK")
print(" SUPPLIER_TOKEN:", mask(SUPPLIER_TOKEN))
print(" SHOPIFY_TOKEN :", mask(SHOPIFY_TOKEN))
print(" DRY_RUN       :", DRY_RUN)
print()

if not SUPPLIER_TOKEN or not SHOPIFY_TOKEN:
    print("ERROR: One or both tokens are missing. Set SUPPLIER_TOKEN and SHOPIFY_TOKEN and re-run.")
    sys.exit(1)

supplier_headers = {"X-Shopify-Access-Token": SUPPLIER_TOKEN, "Content-Type": "application/json"}
shop_headers = {"X-Shopify-Access-Token": SHOPIFY_TOKEN, "Content-Type": "application/json"}

def fetch_all(url, headers, label):
    items = []
    page = 1
    while True:
        resp = requests.get(url, headers=headers, params={"limit": 250, "page": page})
        print(f"[{label}] GET page {page} -> {resp.status_code}")
        try:
            data = resp.json()
        except Exception as e:
            print(f"[{label}] ERROR parsing JSON: {e}")
            print(resp.text[:1000])
            return items, resp.status_code
        batch = data.get("products", [])
        items.extend(batch)
        if not batch or len(batch) < 250:
            break
        page += 1
    return items, resp.status_code

print("1) Fetching supplier products...")
supplier_products, sup_status = fetch_all(SUPPLIER_API, supplier_headers, "SUPPLIER")
print(f" -> Supplier products fetched: {len(supplier_products)} (last status {sup_status})")
print()

print("2) Fetching my Shopify store products...")
shop_products, shop_status = fetch_all(f"{SHOP_API_BASE}/products.json", shop_headers, "MYSHOP")
print(f" -> My store products fetched: {len(shop_products)} (last status {shop_status})")
print()

def sample_list(iterable, n=8):
    return list(islice(iterable, n))

# gather example SKUs and titles
supplier_skus = []
supplier_titles = []
for p in supplier_products:
    supplier_titles.append(p.get("title", "")[:80])
    for v in p.get("variants", []):
        sku = (v.get("sku") or "").strip()
        if sku:
            supplier_skus.append(sku)

shop_skus = []
shop_titles = []
for p in shop_products:
    shop_titles.append(p.get("title", "")[:80])
    for v in p.get("variants", []):
        sku = (v.get("sku") or "").strip()
        if sku:
            shop_skus.append(sku)

print("Supplier: sample titles:", sample_list(supplier_titles))
print("Supplier: sample SKUs   :", sample_list(supplier_skus))
print()
print("MyStore: sample titles  :", sample_list(shop_titles))
print("MyStore: sample SKUs    :", sample_list(shop_skus))
print()

# compare SKUs
set_sup = set(supplier_skus)
set_shop = set(shop_skus)
intersection = set_sup.intersection(set_shop)
print(f"SKU counts -> supplier: {len(set_sup)}, my store: {len(set_shop)}, intersection: {len(intersection)}")
if intersection:
    print(" Sample overlapping SKUs:", sample_list(sorted(intersection)))
else:
    print(" No overlapping SKUs found. (That explains why updates/merge fail)")

# If there is overlap and DRY_RUN is False, propose a single-safe update
if intersection and not DRY_RUN:
    sku_to_test = next(iter(intersection))
    print("\nDRY_RUN is FALSE — attempting a single safe update for SKU:", sku_to_test)
    # find supplier variant details for this SKU
    sup_var = None
    sup_product = None
    for p in supplier_products:
        for v in p.get("variants", []):
            if (v.get("sku") or "").strip() == sku_to_test:
                sup_var = v
                sup_product = p
                break
        if sup_var:
            break
    # find myshop variant & product
    my_prod = None
    my_var = None
    for p in shop_products:
        for v in p.get("variants", []):
            if (v.get("sku") or "").strip() == sku_to_test:
                my_prod = p
                my_var = v
                break
        if my_var:
            break
    if not sup_var or not my_var:
        print("Could not find variant in supplier or my store; aborting test update.")
    else:
        product_id = my_prod["id"]
        variant_id = my_var["id"]
        update_payload = {
            "product": {
                "id": product_id,
                "title": my_prod.get("title"),  # keep store title
                "variants": [
                    {
                        "id": variant_id,
                        # only update price/inventory to test; it will change live values
                        "price": sup_var.get("price", my_var.get("price")),
                        "inventory_quantity": sup_var.get("inventory_quantity", 0)
                    }
                ]
            }
        }
        print("Update payload prepared (not yet sent):")
        print(update_payload)
        # confirm and send
        print("Sending update to Shopify...")
        resp = requests.put(f"{SHOP_API_BASE}/products/{product_id}.json", headers=shop_headers, json=update_payload)
        print("Update response:", resp.status_code, resp.text[:800])
        if resp.status_code == 200:
            print("Test update succeeded for SKU", sku_to_test)
        else:
            print("Test update failed; inspect the response above.")

print("\nDONE. Next steps / common fixes:")
print("- If supplier fetch returned 401/403: regenerate supplier token and ensure it has read_products.")
print("- If my store fetch returned 401/403: regenerate Shopify Admin token and ensure it has read/write products and inventory scopes.")
print("- If NO overlapping SKUs: make sure supplier SKUs exactly match the SKUs in your store (no leading/trailing spaces, same formatting).")
print("- If there are overlaps but updates failed: set DRY_RUN=false and re-run to attempt a single test update (the script will show the payload it sends).")
print("\nPaste the script output here and I’ll interpret it and give the exact next fix.")
