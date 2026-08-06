"""Find the Bid4Assets auction ID for Butte June 2026."""
import requests, re

r = requests.get("https://www.bid4assets.com/storefront/ButteJun26", timeout=30)
text = r.text

# Find all script src attributes
for m in re.finditer(r'<script[^>]*src=["\']([^"\']+)["\']', text):
    src = m.group(1)
    if any(x in src for x in ["js", "script"]):
        print(f"  SRC: {src}")

# Find inline scripts containing relevant functions
for m in re.finditer(r"<script[^>]*>(.*?)</script>", text, re.DOTALL):
    content = m.group(1).strip()
    if len(content) > 50 and ("propertyList" in content or "loadAuctions" in content or "export" in content.lower()):
        print(f"\nRelevant inline script ({len(content)} chars):")
        print(content[:1500])
        break
else:
    print("No inline script found, checking JS files...")
    # Try engagement.js
    try:
        js = requests.get("https://cdn.bid4assets.com/app/mvc/Scripts/engagement.js", timeout=15).text
        if "propertyList" in js or "loadAuctions" in js:
            for kw in ["propertyList", "loadAuctions", "Export", "export"]:
                idx = js.find(kw)
                if idx >= 0:
                    print(f"\nFound '{kw}' in engagement.js:")
                    print(js[max(0,idx-300):idx+500])
    except Exception as e:
        print(f"Error fetching engagement.js: {e}")

    # Try to find any JS with relevant functions
    # The page likely has the function inline or in a dedicated storefront JS
    if "propertyListDownloadWindow" in text:
        print("\nFound 'propertyListDownloadWindow' directly in page HTML!")
        idx = text.find("propertyListDownloadWindow")
        print(text[max(0,idx-200):idx+600])
