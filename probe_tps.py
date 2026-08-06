import requests
from bs4 import BeautifulSoup
import re

PHONE_RE = re.compile(r"\(?\d{3}\)?[\s.\-]\d{3}[\s.\-]\d{4}")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

url = "https://www.anywho.com/people/Robert+Jones/ca/"
r = requests.get(url, headers=HEADERS, timeout=12)
soup = BeautifulSoup(r.text, "html.parser")

# Print first 60 non-empty lines
lines = [l.strip() for l in soup.get_text("\n").split("\n") if l.strip()]
for i, l in enumerate(lines[:60]):
    print(f"{i:3}: {l}")
