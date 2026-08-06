import pandas as pd
import json
import os
import sys

def check_county(county, verified_csv, partial_parquet):
    print(f"\n{'='*40}")
    print(f"HEALTH CHECK: {county.upper()}")
    print(f"{'='*40}")
    
    # 1. Stage 1 Check (Document Numbers)
    if os.path.exists(verified_csv):
        df_stg1 = pd.read_csv(verified_csv, low_memory=False)
        total_stg1 = len(df_stg1)
        if 'v_document_number' in df_stg1.columns:
            doc_hits = df_stg1['v_document_number'].notna().sum()
            print(f"STAGE 1 (Tax) -> {doc_hits}/{total_stg1} rows with v_document_number ({doc_hits/total_stg1*100:.1f}%)")
        else:
            print(f"STAGE 1 (Tax) -> ERROR: No v_document_number column found")
    else:
        print(f"STAGE 1 (Tax) -> FILE NOT FOUND: {verified_csv}")
        
    # 2. Stage 2 Check (Recorder Enrichment)
    if os.path.exists(partial_parquet):
        df_stg2 = pd.read_parquet(partial_parquet)
        total_stg2 = len(df_stg2)
        
        owner_hits = 0
        doctype_hits = 0
        
        for _, row in df_stg2.iterrows():
            try:
                v = json.loads(row.get('owner_vesting', '{}'))
                if v.get('primary_name'):
                    owner_hits += 1
                if v.get('vesting_doc_type'):
                    doctype_hits += 1
            except:
                pass
                
        print(f"STAGE 2 (Rec) -> Processed {total_stg2} rows so far")
        if total_stg2 > 0:
            print(f"              -> {owner_hits}/{total_stg2} with owner names ({owner_hits/total_stg2*100:.1f}%)")
            print(f"              -> {doctype_hits}/{total_stg2} with doc types ({doctype_hits/total_stg2*100:.1f}%)")
    else:
        print(f"STAGE 2 (Rec) -> PARQUET NOT FOUND (or not started): {partial_parquet}")

if __name__ == "__main__":
    counties = [
        ("shasta", "shasta/shasta_15_percent_sample_VERIFIED.csv", "shasta/shasta_15_percent_sample_VERIFIED_ENRICHED_partial.parquet"),
        ("tehama", "tehama/tehama_15_percent_sample_VERIFIED.csv", "tehama/tehama_15_percent_sample_VERIFIED_ENRICHED_partial.parquet"),
        ("butte", "butte/butte_15_percent_sample_VERIFIED.csv", "butte/butte_test_20_ENRICHED_partial.parquet") # Just using the test batch for butte right now
    ]
    for c, csv_f, pq_f in counties:
        check_county(c, csv_f, pq_f)
    print()
