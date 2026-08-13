# Pre-Auction Property Intelligence Dossier: {{apn_dash}}

**County**: {{county_name}} County, CA  
**Source Identifier**: `{{source_identifier}}` ({{source_identifier_type}})  
**Assessor APN**: `{{assessor_apn}}`  
**Assessor APN Verification Status**: {{assessor_apn_verification_status}}  
**Opportunity Tier**: **{{opportunity_tier}}**  
**Generated Date**: {{generated_date}}  

**🔔 PUBLIC-RECORD SIGNAL: {{priority_signal}}**

---

## 🎯 Executive Opportunity Summary

| Metric | Score / Value |
|---|---|
| **Opportunity Tier** | **{{opportunity_tier}}** |
| **Seller Intent Score** | **{{seller_intent_score}} / 100** |
| **Estimated Equity Ratio** | **{{equity_ratio_pct}}%** |
| **Equity / Assessed-Value Indicator** | **{{equity_signal}}** |
| **Minimum Starting Bid** | ${{min_bid}} |
| **Net Assessed Total Value** | ${{assessed_value}} |
| **Predicted Auction Window** | {{predicted_auction_window}} |

> ⚠️ The Equity / Assessed-Value Indicator above is derived from available valuation and recorded amount data only. It is **not** a title search, lien-priority analysis, encumbrance review, or legal conclusion.

---

## 🏡 Property & Ownership Profile

- **Owner of Record**: **{{owner_name}}**
- **Owner Entity Type**: {{entity_type}}
- **Out-of-State Owner**: {{is_out_of_state_owner}}
- **Property Situs Address**: {{situs}}
- **Land Use Code**: {{use_code}}
- **Acreage / Lot Size**: {{lot_size}} acres
- **Tax Delinquency Status**: {{tax_status}} (Defaulted: {{tax_default_year}})

---

## 📄 Recorder & Encumbrance Provenance

- **Last Recorded Doc Number**: `{{doc_number}}` (Recorded: {{deed_date}})
- **Documentary Transfer Tax**: ${{transfer_tax}} *(Calculated Transfer Consideration: ${{transfer_price}})*
- **Open Encumbrance Count**: {{doc_count}} recorded instruments
- **Notice of Power to Sell / Default**: {{notice_status}}

---

## 🎯 Active Buyer Match Intelligence

- **Matched Buyer Segment**: {{matched_buyers_count}}
- **Top Buyer Match**: {{top_matched_buyer}} *(Score: {{top_buyer_score}})*

---

## 📊 Provenance & Data Audit Trail

- **Primary Source Endpoint**: `{{source_url_or_file}}`
- **Data Integrity Status**: {{verification_status}}
- **Data Gap Audit**: {{data_gaps}}

---

## 🧭 Auction Identity & Operational Status

> ⚠️ This section reflects locally matched and/or historical source records only. It is **not** proof of a current, live, official auction listing unless `auction_identity_status` below is `live_confirmed`, and is never a title, ownership, lien-priority, or legal-status conclusion.

**1. Auction Identity**
- **Auction/Listing ID**: `{{auction_listing_id}}`
- **Auction Identity Status**: {{auction_identity_status}}

**2. Tax / Default / Reconciliation Status**
- **Property Tax / Default Status**: {{property_tax_status}}
- **Reconciliation / Exclusion Reason**: {{reconciliation_or_exclusion_reason}}
- **Source Document Summary**: {{source_document_summary}}

**3. Source Provenance**
- **Source Artifact & Reference**: `{{status_source_artifact_ref}}`

**4. Freshness**
- **Retrieval / Last-Confirmed Timestamp**: {{source_retrieval_timestamp}}
- **Freshness Status**: {{freshness_status}}

**5. Timing**
- **Auction Timing Type**: {{auction_timing_type}}
- **Auction Window**: {{auction_window_labeled}}
- **Exact Deadline**: {{auction_deadline}}

---
*Generated automatically by CA-UNIFY Engine | Verified Public Source Data*
