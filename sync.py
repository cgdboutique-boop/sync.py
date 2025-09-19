import os
import json
import requests

# -------------------------------
# CONFIG (from environment variables / GitHub secrets)
# -------------------------------
SHOPIFY_STORE = os.environ.get("SHOPIFY_STORE")
SHOPIFY_TOKEN = os.environ.get("SHOPIFY_TOKEN")

HEADERS = {
    "Content-Type": "application/json",
    "X-Shopify-Access-Token": SHOPIFY_TOKEN
}

# -------------------------------
# SAMPLE PRODUCT DATA
# -------------------------------
product_title = "Sample Product"
product_description = "<strong>Awesome product description</strong>"
product_type = "Toys"
vendor_name = "CGD Kids Boutique"

variants_list = [
    {
        "option1": "Red",
        "price": "99.99",
        "sku": "SKU_RED",
        "inventory_management": "shopify",
        "inventory_quantity": 10
    },
    {
        "option1": "Blue",
        "price": "109.99",
        "sku": "SKU_BLUE",
        "inventory_management": "shopify",
        "inventory_quantity": 5
    }
]

images_list = [
    {"src": "https://example.com/image1.jpg"},
    {"src": "https://example.com/image2.jpg"}
]

# -------------------------------
# STEP 1: CHECK IF PRODUCT EXISTS
# -------------------------------
search_url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products.json?title={product_title}"
search_response = requests.get(search_url, headers=HEADERS)

if search_response.status_code != 200:
    print(f"❌ Failed to search product. Status: {search_response.status_code}")
    print(search_response.text)
    exit()

existing_products = search_response.json().get("products", [])

if existing_products:
    product = existing_products[0]
    product_id = product["id"]
    print(f"🔄 Product exists. Updating Product ID: {product_id}")

    # -------------------------------
    # STEP 2: UPDATE PRODUCT INFO (TITLE, DESCRIPTION, VENDOR)
    # -------------------------------
    product_data = {
        "product": {
            "id": product_id,
            "title": product_title,
            "body_html": product_description,
            "vendor": vendor_name,
            "product_type": product_type
        }
    }
    update_url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products/{product_id}.json"
    update_response = requests.put(update_url, headers=HEADERS, json=product_data)
    if update_response.status_code == 200:
        print("✅ Product info updated")
    else:
        print(f"❌ Failed to update product info. Status: {update_response.status_code}")
        print(update_response.text)

    # -------------------------------
    # STEP 3: UPDATE OR ADD VARIANTS
    # -------------------------------
    existing_variants = {v["option1"]: v for v in product.get("variants", [])}

    for variant in variants_list:
        if variant["option1"] in existing_variants:
            # Update existing variant
            variant_id = existing_variants[variant["option1"]]["id"]
            variant_update_data = {
                "variant": {
                    "id": variant_id,
                    "price": variant["price"],
                    "sku": variant["sku"],
                    "inventory_quantity": variant["inventory_quantity"],
                    "inventory_management": "shopify"
                }
            }
            variant_update_url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/variants/{variant_id}.json"
            v_response = requests.put(variant_update_url, headers=HEADERS, json=variant_update_data)
            if v_response.status_code == 200:
                print(f"✅ Updated variant: {variant['option1']}")
            else:
                print(f"❌ Failed to update variant: {variant['option1']}")
                print(v_response.text)
        else:
            # Add new variant
            new_variant_data = {
                "variant": {
                    "option1": variant["option1"],
                    "price": variant["price"],
                    "sku": variant["sku"],
                    "inventory_quantity": variant["inventory_quantity"],
                    "inventory_management": "shopify"
                }
            }
            create_variant_url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products/{product_id}/variants.json"
            create_response = requests.post(create_variant_url, headers=HEADERS, json=new_variant_data)
            if create_response.status_code == 201:
                print(f"➕ Added new variant: {variant['option1']}")
            else:
                print(f"❌ Failed to add variant: {variant['option1']}")
                print(create_response.text)

    # -------------------------------
    # STEP 4: ADD IMAGES IF NOT ALREADY PRESENT
    # -------------------------------
    existing_images = [img["src"] for img in product.get("images", [])]
    new_images = [img for img in images_list if img["src"] not in existing_images]

    for img in new_images:
        image_url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products/{product_id}/images.json"
        img_data = {"image": {"src": img["src"]}}
        img_response = requests.post(image_url, headers=HEADERS, json=img_data)
        if img_response.status_code == 201:
            print(f"🖼 Added new image: {img['src']}")
        else:
            print(f"❌ Failed to add image: {img['src']}")
            print(img_response.text)

else:
    # -------------------------------
    # PRODUCT DOES NOT EXIST → CREATE NEW PRODUCT
    # -------------------------------
    print("➕ Product not found. Creating new product...")
    product_data = {
        "product": {
            "title": product_title,
            "body_html": product_description,
            "vendor": vendor_name,
            "product_type": product_type,
            "variants": variants_list,
            "images": images_list
        }
    }
    create_url = f"https://{SHOPIFY_STORE}/admin/api/2025-07/products.json"
    create_response = requests.post(create_url, headers=HEADERS, json=product_data)
    if create_response.status_code == 201:
        print("✅ Product created successfully!")
    else:
        print(f"❌ Failed to create product. Status: {create_response.status_code}")
        print(create_response.text)
