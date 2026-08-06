import requests, re, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0.0.0 Safari/537.36"}
for q in ["fresno county clerk recorder online index search", "fresno county recorder grantor grantee search"]:
    r = requests.get("https://duckduckgo.com/html/", params={"q": q}, headers=HEADERS, timeout=15)
    print("=== query:", q, "status:", r.status_code)
    for m in re.findall(r'uddg=([^&"]+)', r.text):
        try:
            from urllib.parse import unquote
            print("  ", unquote(m)[:130])
        except Exception:
            pass
