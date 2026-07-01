import os
import requests
import google.auth
import google.auth.transport.requests
from google.cloud import firestore

# Configuration
PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "YOUR_GCP_PROJECT_ID_HERE")
CLOUD_RUN_URL = os.environ.get("CLOUD_RUN_URL", "https://YOUR-SERVICE-URL.a.run.app/enrich")

def get_iam_token(target_audience):
    """Generates an OIDC token for authenticating with the Cloud Run service."""
    creds, project = google.auth.default()
    auth_req = google.auth.transport.requests.Request()
    
    # Refresh to get ID token
    from google.oauth2 import id_token
    return id_token.fetch_id_token(auth_req, target_audience)

def run_cron():
    print("Starting Nightly Recorder Refresh...")
    db = firestore.Client(project=PROJECT_ID)
    
    # Query leads that are not verified
    leads_ref = db.collection("leads").where("verification_status", "!=", "Verified").stream()
    
    # Get IAM token for Cloud Run
    try:
        token = get_iam_token(CLOUD_RUN_URL)
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
    except Exception as e:
        print(f"Failed to get IAM token. Ensure you have ADC configured: {e}")
        return

    for doc in leads_ref:
        lead = doc.to_dict()
        apn = lead.get("apn")
        owner_name = lead.get("owner_name")
        
        if not owner_name:
            continue
            
        print(f"Enriching {apn} - {owner_name}")
        
        # Call Cloud Run Service
        payload = {
            "apn": apn,
            "owner_name": owner_name
        }
        
        try:
            r = requests.post(CLOUD_RUN_URL, json=payload, headers=headers, timeout=120)
            if r.status_code == 200:
                result = r.json()
                
                # Update Firestore with the new fields
                db.collection("leads").document(doc.id).update({
                    "ownership_conflict": result.get("ownership_conflict"),
                    "current_owner_candidate": result.get("current_owner_candidate"),
                    "former_owner": result.get("former_owner"),
                    "active_mortgage": result.get("active_mortgage"),
                    "verification_status": result.get("verification_status"),
                    "latest_transfer_doc": result.get("latest_transfer_doc"),
                    "recorder_checked_at": firestore.SERVER_TIMESTAMP
                })
                print(f"  -> Success: updated {doc.id} (Status: {result.get('verification_status')})")
            else:
                print(f"  -> Error {r.status_code}: {r.text}")
        except Exception as e:
            print(f"  -> Request failed: {e}")

if __name__ == "__main__":
    run_cron()
