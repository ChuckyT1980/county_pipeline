# MISSION

**"Build a reusable platform that converts fragmented county public records into verified, decision-ready property intelligence."**

## Roles
* **Architecture & Product:** Make sure we're building the right thing.
* **Implementation:** Build it efficiently.
* **Reality Check:** Let buyers decide what survives. (Neither of us gets to overrule the market).

## Milestone 1 Complete
- [x] Tehama adapter works reliably
- [x] Data normalized
- [x] Top opportunities verified
- [x] Buyer-ready export created
- [ ] One experienced investor reviews it
- [ ] Feedback documented
- [ ] First paid sale OR clear improvements identified

*Everything else is deferred.*

## Decision Filter
Before adding any feature, ask:
1. Does this help an investor make a better acquisition decision?
2. Can we explain its value in one sentence?
3. Will at least one current buyer likely care?
4. Does it make the platform more reusable?

*If the answer to any of these is "no," the feature goes into the backlog.*

## SYSTEM MODEL
We operate a 3-layer entity system:

### 1. Distress Event Layer
- tax delinquency notices, foreclosure signals, legal publications
→ time-based signals

### 2. Property Core Layer
- APN (normalized + namespaced)
- county identity resolution
→ stable entity anchor

### 3. Property Snapshot Layer
- assessor / county GIS data
- land use, value, geography
→ static asset truth

## JOIN LOGIC
All records resolve through: `county + "|" + normalized_apn`

## VALUE CREATION
Value only exists after: **Distress Event + Property Snapshot merge**

## PRINCIPLE
We do not sell lists. We sell reconciled property intelligence.
