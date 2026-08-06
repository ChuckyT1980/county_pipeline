"""
verification/ — multi-layer data verification substrate.

Every pipeline stage that writes to the CRM output should also write
provenance + flags here. Downstream layers (completeness, consistency,
graph, ownership, outcome) read from this same store.

Usage:
    from verification.writer import VerificationRun

    with VerificationRun(county="butte", cycle_label="Aug 2026 auction",
                         input_source="butte_SCORED_...csv", parcel_count=105) as run:
        for parcel in parcels:
            run.record_field(parcel.apn, "owner_name", parcel.owner,
                             source="recorder_chain_grantee", confidence=0.9)
            run.record_field(parcel.apn, "mailing_address", parcel.mail,
                             source="taxbill_v2", confidence=0.85)
            run.record_parcel(parcel.apn, sources_expected=["asr_print","taxbill_v2","recorder_chain"],
                              sources_succeeded=["asr_print","taxbill_v2"])
"""
from .writer import VerificationRun, connect  # re-exports for convenience
