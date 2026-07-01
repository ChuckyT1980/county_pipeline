import pandas as pd
from google.cloud import firestore

PROJECT_ID = "YOUR_GCP_PROJECT_ID_HERE"

def export_firestore_to_csv():
    print("Exporting Firestore leads to local CSV...")
    db = firestore.Client(project=PROJECT_ID)
    
    leads_ref = db.collection("leads").stream()
    
    docs = []
    for doc in leads_ref:
        docs.append(doc.to_dict())
        
    if not docs:
        print("No leads found in Firestore.")
        return
        
    df = pd.DataFrame(docs)
    
    output_file = "../tax_pipeline/tehama_FIRESTORE_export.csv"
    df.to_csv(output_file, index=False)
    
    print(f"Exported {len(docs)} leads to {output_file}")

if __name__ == "__main__":
    export_firestore_to_csv()
