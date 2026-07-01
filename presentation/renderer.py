import pandas as pd
import glob
import os
from jinja2 import Environment, FileSystemLoader

def find_latest_csv():
    # Prioritize the HTML-Verified Audit file
    if os.path.exists("VERIFIED_AUDIT.csv"):
        return "VERIFIED_AUDIT.csv"
        
    # Fallback to the probabilistic engine output
    csv_files = glob.glob("A_PLUS_TEHAMA_PROB*.csv")
    if not csv_files:
        csv_files = glob.glob("A_PLUS_TEHAMA*.csv") # fallback
    if not csv_files:
        raise FileNotFoundError("No input CSVs found.")
    latest_file = max(csv_files, key=os.path.getctime)
    return latest_file

def render_artifacts():
    print("Loading latest pipeline export...")
    csv_path = find_latest_csv()
    df = pd.read_csv(csv_path)
    
    # Map raw_owner to Lead Name if reading the probabilistic export
    if "raw_owner" in df.columns and "Lead Name" not in df.columns:
        df["Lead Name"] = df["raw_owner"]
        
    # Map DOM Verification fields to presentation fields if they exist
    if "v_situs_address" in df.columns:
        # Only overwrite if the DOM scraper actually found something
        df["situs_address"] = df["v_situs_address"].replace("", pd.NA).fillna(df.get("situs_address", ""))
    
    if "v_portal_total_balance" in df.columns:
        # Use live balance if found, else fallback to original amount_due from county PDF
        df["amount_due"] = df["v_portal_total_balance"].replace("", pd.NA).fillna(df.get("amount_due", ""))
        
    if "v_verification_result" in df.columns:
        df["decision_label"] = df["v_verification_result"] + " (DOM Verified)"
    
    # Fill NaN values to prevent Jinja2 from rendering "nan" on the HTML page
    df = df.fillna("")
    
    leads = df.to_dict('records')
    
    # Calculate macro stats for the investor summary
    stats = {
        "lead_count": len(leads),
        "avg_score": round(df["final_score"].mean(), 1) if not df.empty else 0,
        "max_score": round(df["final_score"].max(), 1) if not df.empty else 0,
        "total_due": f"{pd.to_numeric(df['amount_due'], errors='coerce').sum():,.2f}" if not df.empty else "0.00"
    }
    
    # Setup Jinja2 Environment targeting the templates folder
    env = Environment(loader=FileSystemLoader("presentation/templates"))
    
    # Ensure output directory exists
    os.makedirs("presentation/output", exist_ok=True)
    
    print("1. Rendering Beautiful Lead Book (HTML Print-Optimized)...")
    book_template = env.get_template("lead_book.html")
    with open("presentation/output/lead_book.html", "w", encoding='utf-8') as f:
        f.write(book_template.render(leads=leads))
        
    print("2. Rendering Interactive Dashboard...")
    dash_template = env.get_template("dashboard.html")
    with open("presentation/output/dashboard.html", "w", encoding='utf-8') as f:
        f.write(dash_template.render(leads=leads, stats=stats))
        
    print("3. Rendering Investor Summary...")
    sum_template = env.get_template("summary.html")
    with open("presentation/output/summary.html", "w", encoding='utf-8') as f:
        f.write(sum_template.render(stats=stats))
        
    print("4. Generating Streamlined CRM CSV...")
    # Export logic for the slim CRM CSV
    try:
        crm_out = df[["final_score", "Lead Name", "apn", "amount_due", "persistence_years", "headline"]].copy()
        crm_out.columns = ["Lead Score", "Owner", "Property APN", "Amount Due", "Years in Default", "Notes"]
        crm_out["Phone"] = ""
        crm_out["Email"] = ""
        # Reorder to match the requested format
        crm_out = crm_out[["Lead Score", "Owner", "Property APN", "Phone", "Email", "Amount Due", "Years in Default", "Notes"]]
        crm_out.to_csv("presentation/output/crm_streamlined.csv", index=False)
    except Exception as e:
        print(f"Warning: Could not create streamlined CSV due to missing columns: {e}")
    
    print("\n[SUCCESS] Presentation Engine Complete.")
    print("All commercial-grade artifacts are now available in the 'presentation/output/' directory.")

if __name__ == "__main__":
    render_artifacts()
