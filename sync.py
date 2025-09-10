import requests
import os
import re

# -----------------------------
# Configuration
# -----------------------------
SUPPLIER_API_URL = "https://the-brave-ones-childrens-fashion.myshopify.com/admin/api/2023-10/products.json"
SUPPLIER_TOKEN = os.getenv("SUPPLIER_TOKEN")

SHOP_URL = "https://cgdboutique.myshopify.com/admin/api/2023-10"
SHOPIFY_TOKEN = os.getenv("SHOPIFY_TOKEN")

LOCATION_ID = 79714615616  # Shopify Location ID for inventory

supplier_headers = {"X-Shopify-Access-Token": SUPPLIER_TOKEN}
shopify_headers = {"X-Shopify-Access-Token": SHOPIFY_TOKEN, "Content-Type": "application/json"}

# -----------------------------
# Helper Functions
# -----------------------------
def clean_text(text):
    if not text:
        return ""
    text = re.sub(r"<\/?p>", "", text)
    text = re.sub(r"Â", "", text)
    text = re.sub(r"<\/?span.*?>", "", text)
    text = re.sub(r'data-mce-fragment="1"', "", text)
    return text.strip()

def extract_sku(text):
    """Extract numeric SKU from supplier title"""
    if not text:
        return None
    match = re.search(r'\b\d+\b', text)
    return match.group(0) if match else None
