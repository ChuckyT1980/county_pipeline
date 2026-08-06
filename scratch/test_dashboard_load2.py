"""Test dashboard data loading - bypass streamlit caching"""
import sys, os, types
base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, base)

# Import COUNTY_CONFIG directly (it's a normal dict, no streamlit)
from dashboard import COUNTY_CONFIG

# Get the underlying load_data function without the streamlit cache decorator
import dashboard
load_data_impl = dashboard.load_data.__wrapped__ if hasattr(dashboard.load_data, '__wrapped__') else dashboard.load_data

for name in COUNTY_CONFIG:
    cfg = COUNTY_CONFIG[name]
    csv_path = cfg['csv']
    exists = os.path.exists(os.path.join(base, csv_path))
    print("  %-15s %s: %s" % (name, "OK" if exists else "MISSING", csv_path))

print()
for name in COUNTY_CONFIG:
    cfg = COUNTY_CONFIG[name]
    try:
        # Call the wrapped function (the actual implementation)
        df, snap_map = load_data_impl(cfg)
        print("%s: %d rows, %d snapshots" % (name, len(df), len(snap_map)))
        if len(df) > 0:
            if "active_liens" in df.columns:
                print("  Sum liens: %d" % df["active_liens"].sum())
            print("  First 3 rows:")
            for _, r in df.head(3).iterrows():
                print("    %-35s liens=%-3s bal=%-8s" % (str(r.get("Owner","?"))[:35], r.get("active_liens","?"), r.get("Default Balance","?")))
    except Exception as e:
        print("%s: ERROR: %s" % (name, e))
        import traceback
        traceback.print_exc()
