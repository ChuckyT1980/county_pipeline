"""
ShastaAddressOwnerAdapter — queries ParcelAssesseeSitus FeatureServer
by ASMT (12-digit APN) for owner, situs, deed refs, acreage, tax links.
"""
import requests, json, time, os
import pandas as pd
from pathlib import Path
from datetime import datetime, timezone

ENDPOINT = "https://gis.shastacounty.gov/arcgis/rest/services/OpenData/ParcelAssesseeSitus/FeatureServer/0/query"
OUT_FIELDS = "APN,ASMT,APN_Dash,Situs_Address,Assessee,Assessee_Address,Current_Doc_Num,Current_Doc_Date,Recorded_Acres,GIS_Acres,TRA,Assr_Link,Tax_Link"
BATCH_SIZE = 50
RATE_LIMIT = 0.1

def clean_apn(raw):
    if not raw or str(raw).strip() in ("", "nan", "None"):
        return ""
    return str(raw).strip().replace("-", "").replace(".0", "").replace(",", "").replace(" ", "")

def query_asmt(asmt):
    params = {
        "where": f"ASMT='{asmt}'",
        "outFields": OUT_FIELDS,
        "returnGeometry": "false",
        "f": "json"
    }
    try:
        r = requests.get(ENDPOINT, params=params, timeout=15)
        if r.status_code == 200:
            data = r.json()
            if data.get("features"):
                return data["features"][0]["attributes"]
    except Exception:
        pass
    return None

def query_batch(asmt_list, label=""):
    results = {}
    n = len(asmt_list)
    for i, asmt in enumerate(asmt_list):
        if not asmt:
            continue
        result = query_asmt(asmt)
        if result:
            results[asmt] = result
        if (i + 1) % 10 == 0:
            print(f"  {label} [{i+1}/{n}]", flush=True)
        time.sleep(RATE_LIMIT)
    return results

def enrich_shasta(input_csv, output_csv):
    print(f"Loading: {input_csv}")
    df = pd.read_csv(input_csv)
    shasta = df[df["county"].astype(str).str.lower() == "shasta"].copy()
    print(f"Shasta rows: {len(shasta)}")

    # Build ASMT lookup from fee_parcel or apn or asmt
    asmt_raw = shasta.get("asmt", shasta.get("fee_parcel", shasta.get("apn", "")))
    shasta["asmt_key"] = asmt_raw.astype(str).apply(clean_apn)

    # Deduplicate
    unique_asmts = shasta["asmt_key"].dropna().unique().tolist()
    unique_asmts = [a for a in unique_asmts if a]
    print(f"Unique ASMT keys: {len(unique_asmts)}")

    # Query
    results = query_batch(unique_asmts, "FS")

    # Map results back
    doc_num_map = {}
    deed_date_map = {}
    situs_map = {}
    assessee_map = {}
    assessee_addr_map = {}
    recorded_acres_map = {}
    gis_acres_map = {}
    tra_map = {}
    assr_link_map = {}
    tax_link_map = {}

    for asmt, attrs in results.items():
        doc_num_map[asmt] = attrs.get("Current_Doc_Num", "")
        raw_ts = attrs.get("Current_Doc_Date")
        if raw_ts:
            try:
                dt = datetime.fromtimestamp(raw_ts / 1000, tz=timezone.utc)
                deed_date_map[asmt] = dt.strftime("%Y-%m-%d")
            except:
                deed_date_map[asmt] = ""
        else:
            deed_date_map[asmt] = ""
        situs_map[asmt] = attrs.get("Situs_Address", "")
        assessee_map[asmt] = attrs.get("Assessee", "")
        assessee_addr_map[asmt] = attrs.get("Assessee_Address", "")
        recorded_acres_map[asmt] = attrs.get("Recorded_Acres", "")
        gis_acres_map[asmt] = attrs.get("GIS_Acres", "")
        tra_map[asmt] = attrs.get("TRA", "")
        assr_link_map[asmt] = attrs.get("Assr_Link", "")
        tax_link_map[asmt] = attrs.get("Tax_Link", "")

    shasta["fs_doc_number"] = shasta["asmt_key"].map(doc_num_map)
    shasta["fs_deed_date"] = shasta["asmt_key"].map(deed_date_map)
    shasta["fs_situs"] = shasta["asmt_key"].map(situs_map)
    shasta["fs_assessee"] = shasta["asmt_key"].map(assessee_map)
    shasta["fs_assessee_address"] = shasta["asmt_key"].map(assessee_addr_map)
    shasta["fs_recorded_acres"] = shasta["asmt_key"].map(recorded_acres_map)
    shasta["fs_gis_acres"] = shasta["asmt_key"].map(gis_acres_map)
    shasta["fs_tra"] = shasta["asmt_key"].map(tra_map)
    shasta["fs_assr_link"] = shasta["asmt_key"].map(assr_link_map)
    shasta["fs_tax_link"] = shasta["asmt_key"].map(tax_link_map)
    shasta["fs_found"] = shasta["asmt_key"].isin(results).astype(int)

    # Fill gaps in our master data using FS results
    before_owner = shasta["owner_name"].notna().sum()
    before_situs = shasta["situs_address"].notna().sum()
    before_acres = shasta["acres"].notna().sum()
    before_doc = shasta["rec_doc_number"].notna().sum()

    # Fill owner_name where empty
    owner_mask = shasta["owner_name"].isna() | shasta["owner_name"].astype(str).str.strip().eq("")
    shasta.loc[owner_mask, "owner_name"] = shasta.loc[owner_mask, "fs_assessee"]

    # Fill situs_address where empty
    situs_mask = shasta["situs_address"].isna() | shasta["situs_address"].astype(str).str.strip().eq("")
    shasta.loc[situs_mask, "situs_address"] = shasta.loc[situs_mask, "fs_situs"]

    # Fill acres where empty (convert to float)
    acres_mask = shasta["acres"].isna() | shasta["acres"].astype(str).str.strip().eq("")
    fill_acres = pd.to_numeric(shasta.loc[acres_mask, "fs_recorded_acres"], errors="coerce")
    shasta.loc[acres_mask, "acres"] = fill_acres

    # Fill rec_doc_number where empty (use FS deed number)
    doc_mask = shasta["rec_doc_number"].isna() | shasta["rec_doc_number"].astype(str).str.strip().eq("")
    shasta.loc[doc_mask, "rec_doc_number"] = shasta.loc[doc_mask, "fs_doc_number"]

    after_owner = shasta["owner_name"].notna().sum()
    after_situs = shasta["situs_address"].notna().sum()
    after_acres = shasta["acres"].notna().sum()
    after_doc = shasta["rec_doc_number"].notna().sum()

    print(f"\nCoverage improvement:")
    print(f"  owner_name:       {before_owner} -> {after_owner}")
    print(f"  situs_address:    {before_situs} -> {after_situs}")
    print(f"  acres:            {before_acres} -> {after_acres}")
    print(f"  rec_doc_number:   {before_doc} -> {after_doc}")
    print(f"  FS found:         {shasta['fs_found'].sum()}/{len(shasta)}")

    # Save
    shasta.to_csv(output_csv, index=False)
    print(f"\nSaved: {output_csv} ({len(shasta)} rows)")

if __name__ == "__main__":
    base = Path(__file__).parent.parent
    enrich_shasta(
        base / "northern_ca_MASTER_merged.csv",
        base / "shasta_fs_enriched.csv"
    )
