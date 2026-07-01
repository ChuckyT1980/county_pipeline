import re

def classify(docs: list, owner_name: str) -> dict:
    flags = {
        "ownership_conflict": False,
        "current_owner_candidate": owner_name,
        "former_owner": None,
        "active_mortgage": False,
        "estate_flag": False,
        "npts_active": False,
        "consecutive_tax_liens": 0,
        "lien_clear": True,
        "verification_status": "Unverified",
        "latest_transfer_doc": None,
        "recorder_rows": docs
    }

    # Count mortgages and reconveyances to compute net
    raw_mortgages = 0
    raw_reconveyances = 0
    latest_deed_date = ""

    search_last = owner_name.split(",")[0].strip().upper()
    search_first = ""
    if "," in owner_name:
        parts = owner_name.split(",")[1].strip().upper().split()
        search_first = parts[0] if parts else ""

    for d in docs:
        t = d.get("doc_type", "").upper()

        if t in ["RECONVEYANCE", "FULL RECONVEYANCE"]:
            raw_reconveyances += 1

        if t in ["DEED OF TRUST", "MORTGAGE"]:
            raw_mortgages += 1

        if t in ["DEED", "GRANT DEED", "QUITCLAIM DEED", "WARRANTY DEED"]:
            grantor_text = str(d.get("grantor", "")).upper()
            grantee_text = str(d.get("grantee", "")).upper()

            if search_last in grantor_text and (not search_first or search_first in grantor_text):
                # Owner is grantor = they sold it
                # But check if grantee is related (same last name, trust, LLC)
                is_related = (search_last in grantee_text or
                              any(w in grantee_text for w in ["TRUST", "LLC", "REVOCABLE", "FAMILY"]))
                if is_related and search_first and search_first in grantee_text:
                    flags["ownership_conflict"] = False  # Self-to-trust transfer
                else:
                    flags["ownership_conflict"] = True
                    flags["former_owner"] = owner_name

                    doc_date = d.get("recording_date", "")
                    if doc_date >= latest_deed_date:
                        flags["current_owner_candidate"] = d.get("grantee", "")
                        flags["latest_transfer_doc"] = d.get("doc_number", "")
                        latest_deed_date = doc_date

        if "ESTATE" in str(d.get("grantor", "")).upper() or "AFFIDAVIT OF DEATH" in t:
            flags["estate_flag"] = True

        if t == "NOTICE OF POWER TO SELL":
            flags["npts_active"] = True

        if "TAX LIEN" in t and "RELEASE" not in t:
            flags["consecutive_tax_liens"] += 1

        if t == "ABSTRACT OF JUDGMENT":
            flags["lien_clear"] = False

    # Net mortgage count (DOTs minus reconveyances)
    flags["active_mortgage"] = max(0, raw_mortgages - raw_reconveyances) > 0

    if not flags["ownership_conflict"] and not flags["active_mortgage"] and flags["lien_clear"]:
        flags["verification_status"] = "Verified"
    elif flags["estate_flag"] or flags["ownership_conflict"] or not flags["lien_clear"]:
        flags["verification_status"] = "Needs Review"

    return flags
