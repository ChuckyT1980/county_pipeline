import httpx

client = httpx.Client(
    base_url="https://common2.mptsweb.com",
    follow_redirects=True,
    headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    },
)

r1 = client.get("/mbc/butte/tax/search")
print("Status after visiting search page:", r1.status_code)
print("Cookies after visiting search page:", dict(client.cookies))

r2 = client.get("/MBC/butte/tax/main/002271003000/2026/0000")
print("Detail page status:", r2.status_code)
print("Contains 'Tax Details':", "Tax Details" in r2.text)
print("Contains 'Delinq. Date':", "Delinq. Date" in r2.text)
