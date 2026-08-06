import glob, os, csv

counties = ['fresno', 'shasta', 'tehama', 'humboldt', 'colusa', 'glenn', 'plumas']

print("=== NON-BUTTE COUNTY DATA INVENTORY ON DISK ===")
for c in counties:
    c_dir = f"data/counties/{c}"
    ep_file = f"{c_dir}/excess_proceeds.csv"
    db_file = f"{c_dir}/state.sqlite"
    
    ep_exists = os.path.exists(ep_file)
    ep_size = os.path.getsize(ep_file) if ep_exists else 0
    
    db_exists = os.path.exists(db_file)
    db_size = os.path.getsize(db_file) if db_exists else 0
    
    dossier_files = glob.glob(f"output/dashboard/{c}_*.md")
    outreach_files = glob.glob(f"output/outreach/{c}/*.md")
    
    db_str = f"YES ({round(db_size/1024,1)}KB)" if db_exists else "NO"
    ep_str = f"YES ({ep_size}b)" if ep_exists else "NO"
    
    print(f"{c.upper():10s} | DB: {db_str:16s} | EP CSV: {ep_str:14s} | Dossiers: {len(dossier_files):3d} | Outreach Letters: {len(outreach_files):3d}")
