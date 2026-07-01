import pandas as pd
import math
from google.cloud import firestore

# Ensure you have run: gcloud auth application-default login
# And set your project ID below
PROJECT_ID = "YOUR_GCP_PROJECT_ID_HERE"

def migrate():
    print("Migrating local CSV to Firestore...")
    db = firestore.Client(project=PROJECT_ID)
    
    df = pd.read_csv("../tax_pipeline/tehama_MASTER_leads_with_liens.csv")
    batch = db.batch()
    count = 0
    
    for _, row in df.iterrows():
        # Clean NaNs
        lead = {k: (v if not (isinstance(v, float) and math.isnan(v)) else None) for k, v in row.to_dict().items()}
        
        # Use APN as document ID if available, else generate one
        apn = str(lead.get("apn_pdf") or lead.get("fee_parcel") or "").strip()
        if not apn or apn == "None":
            doc_ref = db.collection("leads").document()
            apn = doc_ref.id
            lead["apn"] = apn
        else:
            apn = apn.replace(".0", "")
            lead["apn"] = apn
            doc_ref = db.collection("leads").document(apn)
            
        # Ensure owner_name exists
        lead["owner_name"] = str(lead.get("assessee_name", "")).strip()
        if not lead.get("verification_status"):
            lead["verification_status"] = "Unverified"
            
        batch.set(doc_ref, lead)
        count += 1
        
        # Firestore batch size limit is 500
        if count % 400 == 0:
            batch.commit()
            print(f"  Committed {count} leads...")
            batch = db.batch()
            
    if count % 400 != 0:
        batch.commit()
        
    print(f"Successfully migrated {count} leads to Firestore!")

if __name__ == "__main__":
    migrate()
