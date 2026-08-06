import requests

apn = "002271003000"
s = requests.Session()
s.headers.update({'User-Agent': 'Mozilla/5.0'})

# Try various URL patterns for Butte assessor data
urls = [
    # Original AsrPrint pattern (404)
    f"https://common2.mptsweb.com/mbap/butte/asr/AsrPrint/{apn}",
    # Try without mbap subdomain
    f"https://common2.mptsweb.com/butte/asr/AsrPrint/{apn}",
    f"https://common2.mptsweb.com/asr/butte/AsrPrint/{apn}",
    # Try MBC path
    f"https://common2.mptsweb.com/MBC/butte/asr/AsrPrint/{apn}",
    # Try common1
    f"https://common1.mptsweb.com/mbap/butte/asr/AsrPrint/{apn}",
    # Try different endpoint names
    f"https://common2.mptsweb.com/mbap/butte/asr/AsrDetail/{apn}",
    f"https://common2.mptsweb.com/mbap/butte/asr/AsrQuery/{apn}",
    f"https://common2.mptsweb.com/mbap/butte/asr/{apn}",
    # Search page with JSON accept header
    f"https://common2.mptsweb.com/MBC/butte/tax/search?f=Q&Asmt={apn}&TaxYear=2025&RollYear=",
    # Try the detail page with dash-formatted APN
    f"https://common2.mptsweb.com/MBC/butte/tax/main/002-271-003-000/2025/0000",
    # Try without trailing zeros
    f"https://common2.mptsweb.com/mbap/butte/asr/AsrPrint/2271003000",
    # Try the MBC alternate
    f"https://common2.mptsweb.com/MBC/butte/asr/main/{apn}",
]

for url in urls:
    try:
        r = s.get(url, timeout=10)
        print(f"[{r.status_code}] {url[:100]}")
    except Exception as e:
        print(f"[ERR] {url[:100]} -> {str(e)[:60]}")
