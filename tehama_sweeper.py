import requests
import json
import time
from collections import deque, defaultdict

BASE = "https://common1.mptsweb.com/MBC"
SEARCH_ENDPOINT = "/api/search/tehama/0000-CURR"

HEADERS = {
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json",
    "Referer": BASE + "/tehama/tax/search"
}

# -----------------------------
# CONFIG
# -----------------------------
SEEDS = [
    "004", "013", "015", "022", "024",
    "029", "033", "061", "062", "069", "555"
]

MAX_DEPTH = 4              # prevents runaway recursion
MIN_EXPAND_SIZE = 10       # density threshold
RATE_LIMIT_SLEEP = 0.25    # adjust if needed

# -----------------------------
# STATE
# -----------------------------
session = requests.Session()
visited = set()
results_buffer = []

# establish session cookie
session.get(BASE + "/tehama/tax/search")


# -----------------------------
# CORE REQUEST FUNCTION
# -----------------------------
def fetch(field, query):
    url = f"{BASE}{SEARCH_ENDPOINT}/{field}/{query}"

    try:
        r = session.get(url, headers=HEADERS, timeout=10)

        if r.status_code != 200:
            return []

        data = r.json()

        # Custom patch for Tehama's nested string-JSON structure
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except:
                pass

        # normalize response shape
        if isinstance(data, dict):
            rows = data.get("Table", {}).get("Row", [])
            if isinstance(rows, dict):
                return [rows]
            return rows
            
        if isinstance(data, list):
            return data

        return []

    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return []


# -----------------------------
# PERSISTENCE
# -----------------------------
def save_record(record):
    with open("tehama_raw_extract.jsonl", "a") as f:
        f.write(json.dumps(record) + "\n")


# -----------------------------
# DENSITY ANALYSIS
# -----------------------------
def should_expand(records):
    return len(records) >= MIN_EXPAND_SIZE


# -----------------------------
# RECURSIVE EXPANSION ENGINE
# -----------------------------
def expand(prefix, depth=0):
    if prefix in visited:
        return

    visited.add(prefix)

    if depth > MAX_DEPTH:
        return

    print(f"[SCAN] prefix={prefix} depth={depth}")

    # query multiple index fields
    all_records = []

    # Using only feeparcel to expand the APN tree efficiently based on previous learnings
    for field in ["feeparcel", "asmt"]:
        time.sleep(RATE_LIMIT_SLEEP)
        records = fetch(field, prefix)

        if records:
            all_records.extend(records)

    # dedupe simple (by APN/feeparcel if present)
    unique = {json.dumps(r, sort_keys=True) for r in all_records}
    cleaned = [json.loads(r) for r in unique]

    # store
    for r in cleaned:
        save_record({
            "prefix": prefix,
            "depth": depth,
            "record": r
        })

    results_buffer.extend(cleaned)

    # density rule → decide expansion
    if not should_expand(cleaned):
        return

    # expand children only if dense
    # add hyphen if we reach 3 digits to match APN format (e.g. 035 -> 035-0)
    # Tehama format typically XXX-XXX-XXX-000, so after 3 digits comes a hyphen
    for digit in "0123456789":
        if len(prefix) == 3:
            next_prefix = f"{prefix}-{digit}"
        else:
            next_prefix = f"{prefix}{digit}"
        expand(next_prefix, depth + 1)


# -----------------------------
# ENTRY POINT
# -----------------------------
def run():
    print("[START] Tehama adaptive sweep")

    # Clear old extract
    open("tehama_raw_extract.jsonl", "w").close()

    try:
        with open("tehama_seed_prefixes_6.json") as f:
            seeds = json.load(f)
    except:
        seeds = ["035-252"] # fallback

    # Run for the first few seeds to test the depth explosion
    for seed in seeds[:3]:
        expand(seed)

    print("[DONE]")
    print(f"Visited prefixes: {len(visited)}")
    print(f"Records collected: {len(results_buffer)}")


if __name__ == "__main__":
    run()
