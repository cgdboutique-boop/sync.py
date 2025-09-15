import os
import requests
import time
import uuid

# -------------------------------
# CONFIG (from GitHub secrets)
# -------------------------------
SHOPIFY_STORE = os.environ.get("SHOPIFY_STORE")
SHOPIFY_TOKEN = os.environ.get("SHOPIFY_TOKEN")
SUPPLIER_API_URL = os.environ.get("SUPPLIER_API_URL")
SUPPLIER_TOKEN = os.environ.get("SUPPLIER_TOKEN")  # optional

if not SHOPIFY_STORE or not SHOPIFY_TOKEN or not SUPPLIER_API_URL:
    raise ValueError("Please set SHOPIFY_STORE, SHOPIFY_TOKEN and SUPPLIER_API_URL in env.")

SHOP_URL = f"https://{SHOPIFY_STORE}.myshopify.com/admin/api/2025-07"
shopify_headers = {
    "X-Shopify-Access-Token": SHOPIFY_TOKEN,
    "Content-Type": "application/json",
    "Accept": "application/json",
}

supplier_headers = {"Accept": "application/json"}
if SUPPLIER_TOKEN:
    supplier_headers["Authorization"] = f"Bearer {SUPPLIER_TOKEN}"

# -------------------------------
# HELPERS
# -------------------------------
def request_with_retry(method, url, headers=None, json=None, max_retries=5):
    retry_delay = 2
    for attempt in range(max_retries):
        try:
            response = requests.request(method, url, headers=headers, json=json, timeout=30)
            if response is None:
                raise requests.exceptions.RequestException("No response")
            if response.status_code in (429, 401, 422):
                wait = int(response.headers.get("Retry-After", retry_delay))
                print(f"{response.status_code} from {url}. Retrying in {wait}s...")
                time.sleep(wait)
                retry_delay *= 2
                continue
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            print(f"Request error ({method} {url}): {e}. Retrying in {retry_delay}s...")
            time.sleep(retry_delay)
            retry_delay *= 2
    return None

def get_shopify_location_id():
    r = request_with_retry("GET", f"{SHOP_URL}/locations.json", headers=shopify_headers)
    if not r:
        raise RuntimeError("Could not fetch locations from Shopify.")
    locations = r.json().get("locations", [])
    if not locations:
        raise RuntimeError("No locations in Shopify account.")
    print(f"Using location_id {locations[0]['id']}")
    return locations[0]["id"]

# -------------------------------
# SUPPLIER: fetch and normalise product data
# -------------------------------
def fetch_supplier_product(supplier_product_id):
    """Fetch product data from supplier API and normalize to expected fields.

    The supplier API is expected to return JSON with keys like:
      { "id": "...", "title": "...", "description": "...", "variants": [ { "id": "...", "sku": "...", "price": "120", "quantity": 5, "option": "6-12M", "image": "https://..." } ], "images": [ "https://..." ] }
    If your supplier structure differs, edit this function to map the fields.
    """
    url = f"{SUPPLIER_API_URL.rstrip('/')}/products/{supplier_product_id}"
    r = request_with_retry("GET", url, headers=supplier_headers)
    if not r:
        raise RuntimeError(f"Failed to fetch supplier product {supplier_product_id}")
    data = r.json()

    # basic fields with fallbacks:
    product = {
        "supplier_id": data.get("id") or data.get("product_id") or supplier_product_id,
        "title": data.get("title") or data.get("name") or f"Product {supplier_product_id}",
        "body_html": data.get("description") or data.get("body_html") or "",
        "vendor": data.get("vendor") or data.get("brand") or "",
        "product_type": data.get("product_type") or data.get("type") or "",
        "tags": ",".join(data.get("tags", [])) if isinstance(data.get("tags"), list) else (data.get("tags") or ""),
        "handle": data.get("handle") or data.get("slug") or str(data.get("id") or supplier_product_id),
    }

    # Normalise variants:
    raw_variants = data.get("variants") or data.get("items") or []
    variants = []
    for i, v in enumerate(raw_variants):
        sv_id = v.get("id") or v.get("variant_id") or str(uuid.uuid4())
        sku = v.get("sku") or v.get("supplier_sku") or f"{product['supplier_id']}-{sv_id}"
        option1 = v.get("option1") or v.get("size") or v.get("name") or f"Option {i+1}"
        price = str(v.get("price") or v.get("retail_price") or v.get("sale_price") or "0.00")
        stock = int(v.get("quantity") or v.get("stock") or v.get("available") or 0)
        images = []
        # variant-level images
        if v.get("images"):
            images = v.get("images")
        elif v.get("image"):
            images = [v.get("image")]
        variants.append({
            "supplier_variant_id": sv_id,
            "option1": option1,
            "sku": sku,
            "price": price,
            "stock": stock,
            "images": images,
        })

    # product-level images
    product_images = data.get("images") or data.get("media") or []
    # dedupe
    product_images = [i for i in product_images if i]

    product["variants"] = variants
    product["images"] = product_images
    return product

# -------------------------------
# SHOPIFY: helpers to find product & map variants
# -------------------------------
def find_shopify_product_by_handle(handle):
    r = request_with_retry("GET", f"{SHOP_URL}/products.json?limit=250", headers=shopify_headers)
    if not r:
        return None
    products = r.json().get("products", [])
    return next((p for p in products if p.get("handle") == handle), None)

def map_shopify_variants(product):
    """Return dicts keyed by sku and barcode for quick lookup."""
    by_sku = {}
    by_barcode = {}
    for v in product.get("variants", []):
        if v.get("sku"):
            by_sku[v["sku"]] = v
        if v.get("barcode"):
            by_barcode[v["barcode"]] = v
    return by_sku, by_barcode

# -------------------------------
# IMAGE helpers
# -------------------------------
def get_existing_shopify_images(product_id):
    r = request_with_retry("GET", f"{SHOP_URL}/products/{product_id}/images.json", headers=shopify_headers)
    return r.json().get("images", []) if r else []

def add_shopify_image(product_id, src, variant_ids=None):
    payload = {"image": {"src": src}}
    if variant_ids:
        payload["image"]["variant_ids"] = variant_ids
    r = request_with_retry("POST", f"{SHOP_URL}/products/{product_id}/images.json", headers=shopify_headers, json=payload)
    return r.json().get("image") if r else None

def update_shopify_image_variant_ids(product_id, image_id, variant_ids):
    payload = {"image": {"id": image_id, "variant_ids": variant_ids}}
    r = request_with_retry("PUT", f"{SHOP_URL}/products/{product_id}/images/{image_id}.json", headers=shopify_headers, json=payload)
    return r.json().get("image") if r else None

# -------------------------------
# CORE sync function
# -------------------------------
def sync_single_supplier_product(supplier_product_id):
    """Fetch supplier product and sync to Shopify"""
    supplier = fetch_supplier_product(supplier_product_id)
    handle = supplier["handle"]

    # 1) Does product exist in Shopify?
    shop_product = find_shopify_product_by_handle(handle)
    created = False

    if not shop_product:
        # Build create payload (we include all variants here)
        create_payload = {
            "product": {
                "title": supplier["title"],
                "body_html": supplier["body_html"],
                "vendor": supplier["vendor"],
                "product_type": supplier["product_type"],
                "tags": supplier["tags"],
                "handle": handle,
                "variants": [],
                "images": [],
            }
        }
        for sv in supplier["variants"]:
            create_payload["product"]["variants"].append({
                "option1": sv["option1"],
                "sku": sv["sku"],
                "price": sv["price"],
                "inventory_management": "shopify",
                # store supplier variant id in barcode so we can map later
                "barcode": sv["supplier_variant_id"],
            })
        # add product-level images (variant associations handled below)
        for img in supplier["images"]:
            create_payload["product"]["images"].append({"src": img})

        r = request_with_retry("POST", f"{SHOP_URL}/products.json", headers=shopify_headers, json=create_payload)
        if not r:
            print("Failed to create product on Shopify")
            return
        shop_product = r.json()["product"]
        created = True
        print(f"Created Shopify product {shop_product['id']} ({handle})")
    else:
        # Update basic product metadata (title, desc, vendor, tags) if needed
        update_payload = {
            "product": {
                "id": shop_product["id"],
                "title": supplier["title"],
                "body_html": supplier["body_html"],
                "vendor": supplier["vendor"],
                "product_type": supplier["product_type"],
                "tags": supplier["tags"]
            }
        }
        r = request_with_retry("PUT", f"{SHOP_URL}/products/{shop_product['id']}.json", headers=shopify_headers, json=update_payload)
        if r:
            shop_product = r.json()["product"]
            print(f"Updated product metadata for {handle}")
        else:
            print("Failed to update product metadata")

    # Refresh mapping of shop variants
    by_sku, by_barcode = map_shopify_variants(shop_product)

    # 2) Ensure every supplier variant exists in Shopify and price is correct
    created_variants = []
    for sv in supplier["variants"]:
        shop_v = by_sku.get(sv["sku"]) or by_barcode.get(sv["supplier_variant_id"])
        if shop_v:
            # update price if needed
            if str(shop_v.get("price")) != str(sv["price"]):
                payload = {"variant": {"id": shop_v["id"], "price": sv["price"]}}
                r = request_with_retry("PUT", f"{SHOP_URL}/variants/{shop_v['id']}.json", headers=shopify_headers, json=payload)
                if r:
                    print(f"Updated price for variant SKU {sv['sku']} -> {sv['price']}")
                else:
                    print(f"Failed to update price for variant SKU {sv['sku']}")
            # ensure barcode (supplier id) is set
            if shop_v.get("barcode") != sv["supplier_variant_id"]:
                payload = {"variant": {"id": shop_v["id"], "barcode": sv["supplier_variant_id"]}}
                r = request_with_retry("PUT", f"{SHOP_URL}/variants/{shop_v['id']}.json", headers=shopify_headers, json=payload)
                if r:
                    print(f"Updated barcode for variant SKU {sv['sku']}")
            # ensure sku stored matches (it should)
            # update our mapping
            # (we will use shop_v for inventory updates)
        else:
            # create variant
            create_variant_payload = {"variant": {
                "option1": sv["option1"],
                "sku": sv["sku"],
                "price": sv["price"],
                "inventory_management": "shopify",
                "barcode": sv["supplier_variant_id"]
            }}
            r = request_with_retry("POST", f"{SHOP_URL}/products/{shop_product['id']}/variants.json", headers=shopify_headers, json=create_variant_payload)
            if r:
                new_v = r.json()["variant"]
                created_variants.append(new_v)
                by_sku[new_v["sku"]] = new_v
                by_barcode[new_v.get("barcode")] = new_v
                print(f"Created variant SKU {sv['sku']} with id {new_v['id']}")
            else:
                print(f"Failed to create variant SKU {sv['sku']}")

    # Refresh full product (variants and images) so we have inventory_item_id and variant ids
    r = request_with_retry("GET", f"{SHOP_URL}/products/{shop_product['id']}.json", headers=shopify_headers)
    if not r:
        print("Failed to re-fetch updated product")
        return
    shop_product = r.json()["product"]
    by_sku, by_barcode = map_shopify_variants(shop_product)

    # 3) Images: associate supplier images to variants
    # Build a mapping src -> [variant_ids]
    image_src_to_variant_ids = {}

    # first, variant-level images (supplier data)
    for sv in supplier["variants"]:
        sku = sv["sku"]
        shop_v = by_sku.get(sku)
        variant_id = shop_v["id"] if shop_v else None
        for img in sv.get("images", []):
            if img:
                image_src_to_variant_ids.setdefault(img, set()).add(variant_id)

    # then, product-level images map to all variants (or leave unassigned)
    for img in supplier["images"]:
        # optionally associate product-level images to no variants; we'll still add them
        image_src_to_variant_ids.setdefault(img, set())

    # fetch existing images and decide create vs update
    existing_images = get_existing_shopify_images(shop_product["id"])
    existing_src_to_image = {img["src"]: img for img in existing_images}

    for src, var_ids in image_src_to_variant_ids.items():
        # convert set to list of actual variant ids (filter out None)
        variant_ids_list = [vid for vid in (var_ids or []) if vid]
        if src in existing_src_to_image:
            image_obj = existing_src_to_image[src]
            # merge variant ids with existing
            existing_variant_ids = image_obj.get("variant_ids") or []
            new_variant_ids = sorted(set(existing_variant_ids) | set(variant_ids_list))
            # update only if changed
            if set(existing_variant_ids) != set(new_variant_ids):
                updated = update_shopify_image_variant_ids(shop_product["id"], image_obj["id"], new_variant_ids)
                print(f"Updated image {src} variant associations -> {new_variant_ids}")
            else:
                print(f"Image {src} already associated correctly")
        else:
            # create image and associate
            img = add_shopify_image(shop_product["id"], src, variant_ids_list if variant_ids_list else None)
            if img:
                print(f"Added image {src} (id {img['id']}) assoc variants {variant_ids_list}")
            else:
                print(f"Failed to add image {src}")

    # 4) Inventory: set inventory levels for each variant using supplier stock
    location_id = get_shopify_location_id()
    for sv in supplier["variants"]:
        sku = sv["sku"]
        shop_v = by_sku.get(sku)
        if not shop_v:
            print(f"No Shopify variant found for SKU {sku}; skipping inventory set.")
            continue
        inventory_item_id = shop_v.get("inventory_item_id")
        if not inventory_item_id:
            print(f"No inventory_item_id for SKU {sku}; skipping.")
            continue
        payload = {
            "location_id": location_id,
            "inventory_item_id": inventory_item_id,
            "available": int(sv["stock"])
        }
        r = request_with_retry("POST", f"{SHOP_URL}/inventory_levels/set.json", headers=shopify_headers, json=payload)
        if r:
            print(f"Set inventory for SKU {sku} -> {sv['stock']}")
        else:
            print(f"Failed to set inventory for SKU {sku}")

    print("Sync complete for supplier product:", supplier_product_id)

# -------------------------------
# RUN (example)
# -------------------------------
if __name__ == "__main__":
    # Replace with supplier product id(s) you want to sync.
    # You can loop this for many supplier product ids.
    supplier_ids_to_sync = [
        "2000133",   # example - change to real supplier product ids
    ]
    for sid in supplier_ids_to_sync:
        try:
            sync_single_supplier_product(sid)
        except Exception as err:
            print(f"Error syncing {sid}: {err}")
