import requests, re
s = requests.Session()
s.headers["User-Agent"] = "Mozilla/5.0"
for url in (f"https://common1.mptsweb.com/mbap/tehama/asr/AsrPrint/085040018000",
            f"https://common1.mptsweb.com/MBC/tehama/tax/main/085040018000/2024/0000"):
    r = s.get(url, timeout=15)
    t = r.text
    print("="*30, url.split("/")[-2] if "tax" not in url else "tax", len(t))
    for m in re.finditer(r"(?i)(owner|assessee|name)", t):
        s_ = max(0, m.start()-60); e_ = min(len(t), m.end()+80)
        snippet = re.sub(r"\s+", " ", t[s_:e_])
        print("  ...", snippet, "...")
