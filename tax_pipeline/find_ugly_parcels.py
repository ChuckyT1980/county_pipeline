"""Find the ugliest, most deceptive parcels for the email teaser."""
import pandas as pd

df = pd.read_csv("butte_auction_enriched.csv")

# Score is already computed — higher = worse/better target
df_sorted = df.sort_values("score", ascending=False)

print(f"Total enriched parcels: {len(df)}")
print()

# Show top 15 highest-scored (ugliest) parcels
print("TOP 15 HIGHEST-SCORE PARCELS (most problematic)")
print("=" * 80)
for _, r in df_sorted.head(15).iterrows():
    print(f"  APN: {r['apn_dash']}")
    print(f"  Address: {r['address']}")
    print(f"  Owner: {r['owner_name']}")
    print(f"  Min Bid: ${r['min_bid']}")
    print(f"  Score: {r['score']}")
    print(f"  Open Mortgages: {r['total_open_mortgages']}")
    print(f"  Liens: {str(r['open_lien_types'])[:120] if pd.notna(r['open_lien_types']) else 'None'}")
    print(f"  NOD: {r['notice_of_default_present']}, AOR: {r['has_assignment_of_rents']}, Trustee Deed: {r['has_trustee_deed']}")
    print(f"  Score Reasons: {r['score_reasons'][:150] if pd.notna(r['score_reasons']) else 'None'}")
    print()

# Find ones with very low min bids but high scores (deceptive cheap)
print()
print("TOP 'DECEPTIVE' — LOW MIN BID + HIGH PROBLEM COUNT")
print("=" * 80)
df["min_bid_num"] = (
    df["min_bid"]
    .astype(str)
    .str.replace(r"[$,]", "", regex=True)
    .str.strip()
)
df["min_bid_num"] = pd.to_numeric(df["min_bid_num"], errors="coerce").fillna(0)

# Parcels under $10k min bid with high problem indicators
deceptive = df[
    (df["min_bid_num"] > 0)
    & (df["min_bid_num"] < 15000)
    & (df["total_open_mortgages"] >= 5)
].sort_values("total_open_mortgages", ascending=False)

for _, r in deceptive.head(10).iterrows():
    print(f"  APN: {r['apn_dash']}")
    print(f"  Address: {r['address']}")
    print(f"  Min Bid: ${r['min_bid']}")
    print(f"  Open Mortgages: {r['total_open_mortgages']}")
    print(f"  NOD: {r['notice_of_default_present']}, Trustee Deed: {r['has_trustee_deed']}")
    print(f"  Liens: {str(r['open_lien_types'])[:120] if pd.notna(r['open_lien_types']) else 'None'}")
    print(f"  Recorder Doc Count: {r['recorder_doc_count']}")
    print()
