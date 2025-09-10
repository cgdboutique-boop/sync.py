- name: Run sync script
  run: python scripts/sync.py
  env:
    SUPPLIER_TOKEN: ${{ secrets.SUPPLIER_TOKEN }}
    SHOPIFY_TOKEN: ${{ secrets.SHOPIFY_TOKEN }}
