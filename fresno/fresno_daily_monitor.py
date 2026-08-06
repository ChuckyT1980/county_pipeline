"""
GovEase & Fresno TTC Daily Monitor
Checks every day for the Fresno County auction list to go live.
Run this manually or schedule it daily starting Aug 1, 2026.
When the list appears, it saves the raw data and sends an alert.
"""
import requests, os, json
from datetime import datetime
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"}
BASE = r"C:\Users\chuck\Downloads\county_pipeline\fresno"
LOG  = os.path.join(BASE, "fresno_monitor_log.csv")
os.makedirs(BASE, exist_ok=True)

def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{ts} | {msg}"
    print(line)
    with open(LOG, "a") as f:
        f.write(line + "\n")

def check_govease_fresno():
    """Check GovEase for any Fresno County auction listing."""
    r = requests.get("https://www.govease.com/auctions", headers=HEADERS, timeout=10)
    soup = BeautifulSoup(r.text, "html.parser")
    text = soup.get_text()
    links = soup.find_all("a", href=True)

    fresno_found = "fresno" in text.lower()
    fresno_links = [l["href"] for l in links if "fresno" in l.get("href","").lower() or "fresno" in l.text.lower()]

    if fresno_found or fresno_links:
        log(f"*** FRESNO FOUND ON GOVEASE *** Links: {fresno_links}")
        # Save raw HTML for scraping
        with open(os.path.join(BASE, "govease_fresno_raw.html"), "w", encoding="utf-8") as f:
            f.write(r.text)
        return True
    else:
        log(f"GovEase checked - Fresno NOT listed yet")
        return False

def check_fatco_fresno():
    """Check if FATCO has published a Fresno ArcGIS layer."""
    r = requests.get("https://www.arcgis.com/sharing/rest/search",
        params={"q": "Fresno County Auction List tax defaulted", "f": "json", "num": 5},
        headers=HEADERS, timeout=10)
    results = r.json().get("results", [])
    fresno_results = [x for x in results if "fresno" in x.get("title","").lower()]
    if fresno_results:
        log(f"*** FATCO FRESNO LAYER FOUND *** {[x.get('title') for x in fresno_results]}")
        with open(os.path.join(BASE, "fatco_fresno_layer.json"), "w") as f:
            json.dump(fresno_results, f, indent=2)
        return True
    else:
        log(f"FATCO checked - No Fresno layer published yet")
        return False

def check_govease_auction_ids():
    """Scan GovEase auction IDs 1349-1400 for any new Fresno listing."""
    for aid in range(1349, 1401):
        url = f"https://liveauctions.govease.com/PublicPortal/RegistrationDetail?AuctionID={aid}&Edit=False/"
        try:
            r = requests.get(url, headers=HEADERS, timeout=5)
            if r.status_code == 200 and len(r.text) > 500:
                if "fresno" in r.text.lower():
                    log(f"*** FRESNO FOUND ON GOVEASE AuctionID={aid} ***")
                    with open(os.path.join(BASE, f"govease_fresno_id{aid}.html"), "w", encoding="utf-8") as f:
                        f.write(r.text)
                    return True
        except Exception:
            pass
    log("GovEase auction ID scan complete - Fresno not found in IDs 1349-1400")
    return False

if __name__ == "__main__":
    log("=== FRESNO DAILY MONITOR RUN ===")
    found = False
    found = check_govease_fresno() or found
    found = check_fatco_fresno() or found
    found = check_govease_auction_ids() or found

    if found:
        log("*** ACTION REQUIRED: Fresno auction data is live. Run fresno_real_pull.py immediately. ***")
    else:
        log("Nothing live yet. Check again tomorrow.")
