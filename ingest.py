import feedparser
import requests
from bs4 import BeautifulSoup
import time

# 1. The Syndication Feed Registry
RSS_FEEDS = {
    # 1. Statewide Combined Public Notices Feed (Legal Notice Syndication Network)
    # This bypasses the search box UI and reads the raw chronological publication feed directly.
    "CA_PUBLIC_NOTICES_STREAM": "https://www.capublicnotice.com/feed",
    
    # 2. Local County Press & Public Notice Syndication (North State Region)
    # Pulls active regional legal distributions covering Butte, Shasta, and Tehama counties.
    "NORTH_STATE_LEGAL_NOTICES": "https://www.actionnewsnow.com/search/?f=rss&t=article&c=news&l=100&q=public+notice",
    
    # 3. Federal Bankruptcy Court (Eastern District of CA - Free Docket Feed)
    # Adding the default calendar routing string forces CM/ECF to stream live daily case activity nodes.
    "FEDERAL_BANKRUPTCY_CAEB": "https://ecf.caeb.uscourts.gov/cgi-bin/ready_rss.pl"
}

def harvest_xml_stream(feed_name, feed_url):
    print(f"[-] Connecting to {feed_name} XML Stream...")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Distress-Engine/1.0"}
    
    try:
        # Use feedparser to handle XML stripping natively
        feed = feedparser.parse(feed_url, response_headers=headers)
        
        raw_text_payload = ""
        entry_count = 0
        
        for entry in feed.entries:
            # Combine the entry title and full text description block
            title = entry.get("title", "")
            summary = entry.get("summary", "")
            
            # Clean out any leftover HTML tags embedded in the XML nodes
            clean_chunk = BeautifulSoup(f"{title} \n {summary}", "html.parser").get_text()
            
            raw_text_payload += f"\n\n--- RSS INGEST STREAM: {feed_name} | {time.strftime('%Y-%m-%d')} ---\n"
            raw_text_payload += clean_chunk
            entry_count += 1
            
        if entry_count > 0:
            with open("data/raw/test_county.txt", "a", encoding="utf-8") as f:
                f.write(raw_text_payload)
            print(f"[✓] Successfully drained {entry_count} nodes from {feed_name} into ingestion deck.")
        else:
            print(f"[!] Stream {feed_name} was active but returned 0 new records.")
            
    except Exception as e:
        print(f"[!] Stream Exception triggered for {feed_name}: {str(e)}")

def run_all_feeds():
    print("=== STARTING 3:00 AM STATEWIDE XML HARVEST ===")
    for name, url in RSS_FEEDS.items():
        harvest_xml_stream(name, url)
        time.sleep(2) # Throttle to ensure zero IP friction
    print("=== HARVEST COMPLETE. REVENUE PIPELINE IS READY ===")

if __name__ == "__main__":
    run_all_feeds()
