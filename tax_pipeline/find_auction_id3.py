"""Find Bid4Assets auction IDs for Butte June 2026."""
import requests, re

headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

# Try storefront 17687 export
r = requests.get("https://www.bid4assets.com/storefront/ExportPropertyList/17687", headers=headers, timeout=15)
print(f"ExportPropertyList/17687: {r.status_code} ({len(r.content)} bytes)")

# Get page and find auction IDs
r2 = requests.get("https://www.bid4assets.com/storefront/ButteJun26", headers=headers, timeout=15)
text = r2.text

# Find auction IDs in URLs
auction_ids = set()
for m in re.finditer(r'/auction/(\d+)', text):
    auction_ids.add(m.group(1))

# Find any numeric IDs near "Auction" or "auction" 
for m in re.finditer(r'[Aa]uction[^=]*[=:]["\']?(\d{5,})', text):
    auction_ids.add(m.group(1))

# Search for the storefront metadata 
# The Kendo data source was embedded: StorefrontId: 17687
# Look for the collection data
collections = re.findall(r'StorefrontCollectionId["\':]\s*(\d+)', text)
print(f"StorefrontCollectionIds: {collections[:20]}")

# PublishedStorefrontCollectionId
pub_ids = re.findall(r'PublishedStorefrontCollectionId["\':]\s*(\d+)', text)
print(f"PublishedStorefrontCollectionIds: {pub_ids[:20]}")

# StorefrontId
storefront_ids = re.findall(r'StorefrontId["\':]\s*(\d+)', text)
print(f"StorefrontIds: {storefront_ids}")

# Deposit ID
deposit_ids = re.findall(r'/deposits/new/(\d+)', text)
print(f"Deposit IDs: {deposit_ids}")

# Individual auction IDs
if auction_ids:
    print(f"\nIndividual auction IDs found: {auction_ids}")
else:
    print("\nNo /auction/XXXXX URLs in base HTML (dynamically loaded)")

# Try to search bid4assets for Butte June 2026
search_url = "https://www.bid4assets.com/search/auctions"
r3 = requests.get(search_url, headers=headers, timeout=15, params={"q": "Butte June 2026"})
print(f"\nSearch: {r3.status_code} ({len(r3.text)} chars)")
if "Butte" in r3.text:
    # Extract auction IDs from search results
    for m in re.finditer(r'/auction/(\d+)', r3.text):
        print(f"  Found: /auction/{m.group(1)}")
