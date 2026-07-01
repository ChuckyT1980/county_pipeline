import json
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from canonical import init_intelligence_record
from signals import generate_signals
from scoring import process_record
from fr1 import reconcile_field

gold_records = [
    {
        "id": "Record 1 (Estate / High Distress / Low Value Trap)",
        "layer_1_facts": {
            "apn": "049-040-021-000",
            "county": "tehama",
            "owner_sources": {
                "assessor": "OVERMAN, FRANKLIN CHARLES DECD EST OF",
                "tax": "FRANKLIN OVERMAN",
                "parcel": "OVERMAN ESTATE"
            },
            "mailing_address": "UNKNOWN",
            "situs_address": "24099 HOGSBACK RD",
            "default_date": "2019-06-01",
            "auction_date": "2025-08-01",
            "amount_raw": "8579.08",
            "land_use": "VACANT",
            "acreage": 0.08,
            "assessed_value": 1200,
            "improvement_value": 0,
            "access_quality": "poor",
            "zoning_class": "rural_residential",
            "parcel_shape": "irregular",
            "improved_vs_vacant": "vacant"
        }
    },
    {
        "id": "Record 2 (High Value / Low Distress / False Positive Trap)",
        "layer_1_facts": {
            "apn": "054-090-012-000",
            "county": "shasta",
            "owner_sources": {
                "assessor": "WILLIAMS FAMILY TRUST",
                "tax": "WILLIAMS, JOHN",
                "parcel": "JOHN WILLIAMS"
            },
            "mailing_address": "San Francisco, CA",
            "situs_address": "456 COTTONWOOD ST",
            "default_date": None,
            "auction_date": None,
            "amount_raw": "1200",
            "land_use": "SFR",
            "acreage": 2.5,
            "assessed_value": 420000,
            "improvement_value": 310000,
            "access_quality": "good",
            "zoning_class": "residential",
            "parcel_shape": "regular",
            "improved_vs_vacant": "improved"
        }
    },
    {
        "id": "Record 3 (Trust / Moderate Distress / Medium Value)",
        "layer_1_facts": {
            "apn": "068-110-004-000",
            "county": "shasta",
            "owner_sources": {
                "assessor": "JENKINS REVOCABLE TRUST",
                "tax": "JENKINS REVOC TR",
                "parcel": "JENKINS REVOCABLE TRUST"
            },
            "mailing_address": "Nevada",
            "situs_address": "321 SHASTA LAKE RD",
            "default_date": "2022-01-01",
            "auction_date": "2025-11-01",
            "amount_raw": "2200",
            "land_use": "SFR",
            "acreage": 0.9,
            "assessed_value": 180000,
            "improvement_value": 140000,
            "access_quality": "moderate",
            "zoning_class": "residential",
            "parcel_shape": "regular",
            "improved_vs_vacant": "improved"
        }
    },
    {
        "id": "Record 4 (Vacant / Low Value / High Distress Trap)",
        "layer_1_facts": {
            "apn": "001-002-003-000",
            "county": "tehama",
            "owner_raw": "UNKNOWN OWNER DECD",
            "mailing_address": None,
            "situs_address": "REMOTE PARCEL",
            "default_date": "2017-01-01",
            "auction_date": None,
            "amount_raw": "4000",
            "land_use": "VACANT",
            "acreage": 0.3,
            "assessed_value": 800,
            "improvement_value": 0,
            "access_quality": "very_poor",
            "zoning_class": "unknown",
            "parcel_shape": "unknown",
            "improved_vs_vacant": "vacant"
        }
    },
    {
        "id": "Record 5 (Clean, Low Distress, Control Case)",
        "layer_1_facts": {
            "apn": "010-020-030-000",
            "county": "tehama",
            "owner_raw": "JOHNSON, SARAH",
            "mailing_address": "240 MAIN ST, TEHAMA CA",
            "situs_address": "240 MAIN ST",
            "default_date": None,
            "auction_date": None,
            "amount_raw": "0",
            "land_use": "SFR",
            "acreage": 0.2,
            "assessed_value": 320000,
            "improvement_value": 280000,
            "access_quality": "excellent",
            "zoning_class": "residential",
            "parcel_shape": "regular",
            "improved_vs_vacant": "improved"
        }
    }
]

for item in gold_records:
    raw = item["layer_1_facts"]
    # We need to explicitly inject the utility fields since init_intelligence_record doesn't map them yet 
    # from raw, let's fix the raw to map correctly in our test script.
    record = init_intelligence_record(raw, raw["county"])
    # Manually inject utility fields for the test since init_intelligence_record doesn't pull them
    record.facts.land_use = reconcile_field({"assessor": raw.get("land_use")})
    record.facts.acreage = raw.get("acreage")
    record.facts.assessed_value = raw.get("assessed_value")
    record.facts.improvement_value = raw.get("improvement_value")
    if str(raw.get("improved_vs_vacant")).lower() == "improved":
        record.facts.improved_vs_vacant = True
    elif str(raw.get("improved_vs_vacant")).lower() == "vacant":
        record.facts.improved_vs_vacant = False
    record.facts.access_quality = raw.get("access_quality")

    generate_signals(record)
    process_record(record)
    
    print(f"--- {item['id']} ---")
    print(f"Signals: {record.signals}")
    print(f"States:  {record.states}")
    print(f"Tier:    {record.opportunity.tier}")
    print(f"Owner:   {record.facts.owner.state} (conf {record.facts.owner.confidence:.2f})")
    print(f"Explain: {record.opportunity.record_explanation}")
    print(f"Attract: {record.opportunity.attractiveness_score:.2f} | Diff: {record.opportunity.resolution_difficulty:.2f}")
    print()
