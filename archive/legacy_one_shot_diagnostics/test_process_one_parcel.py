import json
from unittest.mock import MagicMock
from butte_stage2_pipeline import process_one_parcel
from butte.butte_tax_api import ButteTaxResult
from tyler_recorder_client import RecorderResult

def test_scenarios():
    print("--- Testing Full Success ---")
    mock_tax = MagicMock()
    mock_tax.get_detail.return_value = ButteTaxResult(
        document_number_raw="2024R0030607",
        parcel_number="001-002-003-000",
        address="",
        assessment="",
        tax_year="",
        roll_category="",
        defaulted_taxes=[MagicMock(balance="$1,500.00")]
    )
    
    mock_recorder = MagicMock()
    mock_recorder.get_results.return_value = (
        [RecorderResult(doc_id="1", doc_number="2024-0030607", doc_type="DEED", recording_date="11/25/2024", grantors=["A"], grantees=["B"])],
        1
    )
    
    res1 = process_one_parcel("001-002-003-000", mock_tax, mock_recorder)
    print(json.dumps(res1, indent=2))
    assert res1["error"] == ""
    assert res1["doc_fmt"] == "2024R0030607"
    assert "DEED" in res1["recorder_chain"]

    print("\n--- Testing Legitimate No-Data ---")
    mock_tax.get_detail.return_value = ButteTaxResult(
        document_number_raw="", # no doc number on file
        parcel_number="001-002-004-000",
        address="",
        assessment="",
        tax_year="",
        roll_category="",
        defaulted_taxes=[]
    )
    res2 = process_one_parcel("001-002-004-000", mock_tax, mock_recorder)
    print(json.dumps(res2, indent=2))
    assert res2["error"] == ""
    assert res2["doc_fmt"] == ""
    assert res2["recorder_chain"] == "[]"

    print("\n--- Testing Genuine Error ---")
    mock_tax.get_detail.side_effect = Exception("Connection Timeout")
    res3 = process_one_parcel("001-002-005-000", mock_tax, mock_recorder)
    print(json.dumps(res3, indent=2))
    assert "tax_client error: Exception: Connection Timeout" in res3["error"]
    
    print("\nAll 3 scenarios passed!")

if __name__ == "__main__":
    test_scenarios()
