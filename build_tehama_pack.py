import json
import csv

INPUT = "tehama_raw_extract.jsonl"

tier1 = []
tier2 = []
tier3 = []


def score(record):
    r = record.get("record", {})
    text = json.dumps(r).lower()

    score = 0

    if "tax" in text:
        score += 2
    if "delinquent" in text:
        score += 3
    if "trust" in text:
        score += 2
    if "estate" in text:
        score += 2
    if "commercial" in text:
        score += 2
    if "lien" in text:
        score += 3

    return score


def classify(record):
    s = score(record)

    if s >= 5:
        tier1.append(record)
    elif s >= 2:
        tier2.append(record)
    else:
        tier3.append(record)


def format_row(r):
    rec = r["record"]

    # Handled slight variations in column names like Situs1
    return {
        "apn": rec.get("FeeParcel", "") or rec.get("Asmt", ""),
        "address": rec.get("Situs1", "") or rec.get("Situs", ""),
        "owner": rec.get("Owner1", "") or rec.get("Owner", ""),
        "tier_reason": score(r)
    }


def run():
    with open(INPUT) as f:
        data = [json.loads(line) for line in f]

    for r in data:
        classify(r)

    # WRITE TIER 1 (MVP PRODUCT)
    with open("tier1_export.csv", "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["apn", "address", "owner", "tier_reason"]
        )
        writer.writeheader()

        for r in tier1:
            writer.writerow(format_row(r))

    # WRITE TIER 2
    with open("tier2_export.csv", "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["apn", "address", "owner", "tier_reason"]
        )
        writer.writeheader()

        for r in tier2:
            writer.writerow(format_row(r))

    print("Tier 1:", len(tier1))
    print("Tier 2:", len(tier2))
    print("Tier 3:", len(tier3))


if __name__ == "__main__":
    run()
