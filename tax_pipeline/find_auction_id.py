"""Find the Bid4Assets auction ID for the Butte June 2026 auction."""
import re
import requests

r = requests.get("https://www.bid4assets.com/storefront/ButteJun26", timeout=30)
text = r.text

# Find propertyListDownloadWindow function
idx = text.find("propertyListDownloadWindow")
if idx >= 0:
    print("=== propertyListDownloadWindow ===")
    print(text[max(0, idx-200):idx+600])

# Find loadAuctionsForCollection
idx2 = text.find("loadAuctionsForCollection")
if idx2 >= 0:
    print("\n=== loadAuctionsForCollection ===")
    print(text[max(0, idx2-200):idx2+600])

# Look for API URLs
print("\n=== API Endpoints ===")
for m in re.finditer(r'(/api/[^\s"\'<>]+)', text):
    print(f"  {m.group(1)}")

# Storefront metadata
print("\n=== Storefront Metadata ===")
for m in re.finditer(r'StorefrontId["\':]\s*(\d+)', text):
    print(f"  StorefrontId: {m.group(1)}")
for m in re.finditer(r'/deposits/new/(\d+)', text):
    print(f"  Deposit ID: {m.group(1)}")

# Look for auction IDs in data attributes
print("\n=== Potential Auction IDs ===")
for m in re.finditer(r'(?:auction|Auction|sale|Sale)[-_\s]?[Ii][Dd]\s*[=:]\s*["\']?(\d+)["\']?', text):
    print(f"  {m.group(0)[:80]}")

# Try downloading the property list spreadsheet
print("\n=== Property List Download ===")
# The function likely calls an endpoint like /storefront/ExportPropertyList/STOREID
for m in re.finditer(r'(ExportPropertyList|propertyList|PropertyList|download)', text, re.IGNORECASE):
    ctx = text[max(0, m.start()-100):m.end()+200]
    print(f"  ...{ctx.strip()[:200]}")
