"""Try to discover Bid4Assets internal API endpoints for auction data."""
import requests, re

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json, text/html",
}

# Try the collections read endpoint for each collection
for cid in range(10140, 10153):
    url = f"https://www.bid4assets.com/storefront/readStorefrontCollectionAuctions?storefrontCollectionId={cid}"
    r = requests.get(url, headers=headers, timeout=15)
    if r.status_code == 200 and len(r.text) > 100:
        print(f"Collection {cid}: {r.status_code} ({len(r.text)} chars)")
        # Look for auction IDs
        ids = re.findall(r'["\']auctionId["\']\s*:\s*(\d+)', r.text)
        if ids:
            print(f"  Auction IDs: {ids}")
        # Print beginning
        print(f"  Preview: {r.text[:300]}")
        break
    else:
        print(f"Collection {cid}: {r.status_code} ({len(r.text)} chars)")

# Try the actual auction detail page for a sample parcel
# From our data, APN 050-120-121-000 (1871 Dean Road, Paradise) is in the reoffer
# Let me check if there's a URL pattern like /auction/detail or /auction/XYZ where XYZ is the auction ID
sample_urls = [
    "https://www.bid4assets.com/auction/10023",
    "https://www.bid4assets.com/auction/1280992",
    "https://www.bid4assets.com/auction/17687",
]
for url in sample_urls:
    r = requests.get(url, headers=headers, timeout=15)
    print(f"\n{url}: {r.status_code} ({len(r.text)} chars)")
    if r.status_code == 200:
        if "Butte" in r.text or "bid4assets" in r.text.lower():
            # Extract title
            m = re.search(r'<title>([^<]+)</title>', r.text)
            print(f"  Title: {m.group(1) if m else 'N/A'}")
