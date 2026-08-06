# Kern County Pipeline Handoff & Endpoint Recon Report

> [!IMPORTANT]
> **CRITICAL DIRECTIVE FOR NEXT AGENT:**  
> **Start with the endpoint recon deliverable — don't build the catalog until endpoints are proven.**

---

## Executive Summary & Target Endpoints

This report documents the live endpoint reconnaissance for **Kern County, California** tax-defaulted property data collection.

- **Owner:** Chuck Terrell / Logic Flow Systems (`mrt@logicflowsystems.io`)
- **Business Model:** Cheap lightweight catalog ($299 per-parcel dossier on-demand when buyer orders).
- **Core Rule:** **NO synthetic/fake data.** Every endpoint must be proven live before building catalog rows.

---

## Discovered Live Kern Endpoints (Tested & Proven)

### 1. Kern County Treasurer-Tax Collector (KCTTC)
* **Live Search Portal:** `https://www.kcttc.co.kern.ca.us/Payment/mainsearch.aspx`
* **General Tax Sale Info Page:** `https://www.kcttc.co.kern.ca.us/index.cfm?fuseaction=kcttcinternet.showGeneralTaxSaleInfo`
* **Live Auction Registration (GovEase):** `https://liveauctions.govease.com/PublicPortal/RegistrationDetail?AuctionID=1348&Edit=False/`
* **Response Status:** `HTTP 200 OK`

### 2. Kern County Assessor ArcGIS FeatureServer / GIS
* **GIS REST Service Endpoint:** `https://maps.kerncounty.com/arcgis/rest/services/Kern_AGS_Parcels/MapServer`
* **Geocoding Service:** `https://maps.kerncounty.com/arcgis/rest/services/Public/ITS_Composite_Locator_GOGov/GeocodeServer`
* **Response Status:** `HTTP 200 OK`

### 3. GovEase Auction Platform Index
* **Public Auction Portal:** `https://www.govease.com/auctions`
* **Target Auction Dates for Kern:** September 14–16, 2026
* **Response Status:** `HTTP 200 OK`

---

## Tasks & Instructions for Next Agent

1. **Verify Endpoint Queries (Do Not Build Catalog First):**
   * Prove full pagination and live query response for KCTTC search (`mainsearch.aspx`) and Kern GIS MapServer (`Kern_AGS_Parcels`).
   * Extract 20 real APN tax bill responses live to validate field mapping schemas.

2. **Kern Field Mapping Schema (Kern → Butte Baseline):**
   | Kern Source Field | Standard Field | Butte Equivalent | Description |
   |---|---|---|---|
   | `APN` / `PARCEL_NO` | `apn` | `apn` | 9-digit APN format (e.g. `001-100-01`) |
   | `FEE_OWNER` | `verified_current_owner_name` | `owner_name` | Primary fee simple title holder |
   | `SITUS` | `situs_address` | `situs_address` | Physical property location |
   | `MAIL_ADDR` | `mailing_address` | `mailing_address` | Owner billing address |
   | `TOTAL_TAX_BILLED` | `v_total_balance` | `v_total_balance` | Current defaulted tax balance |
   | `NET_VALUE` | `net_assessed_value` | `net_assessed_value` | Land + Improvements assessed value |

3. **Build Lightweight Delinquency Catalog (Only After Endpoints Proven):**
   * Bucket parcels into Categories A (2-3yr), B (4yr), C (5+yr non-auction), D (5+yr auction block).
