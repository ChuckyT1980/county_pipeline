"""Test dashboard data loading"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Disable streamlit runtime check
import streamlit.runtime.caching.cache_utils as cu
cu.maybe_show_warning = lambda: None  # suppress ScriptRunContext warnings

from dashboard import COUNTY_CONFIG, load_data

for name, cfg in COUNTY_CONFIG.items():
    csv_path = cfg['csv']
    exists = os.path.exists(csv_path)
    print("  %-15s %s: %s" % (name, "OK" if exists else "MISSING", csv_path))

print()
for name in COUNTY_CONFIG:
    cfg = COUNTY_CONFIG[name]
    try:
        # Patch to bypass streamlit caching in non-streamlit context
        import streamlit.runtime.caching as caching
        orig_get_cache_key = caching.cache_resource._CachedFunction._get_or_create_cached_value
        caching.cache_resource._CachedFunction._get_or_create_cached_value = lambda self, *a, **kw: self._info.func(*a, **kw)
        
        df, snap_map = load_data(cfg)
        print("%s: %d rows, %d snapshots" % (name, len(df), len(snap_map)))
        if len(df) > 0:
            cols = ["active_liens","mortgages","owner_name","assessee_name"]
            avail = [c for c in cols if c in df.columns]
            print("  Available cols: %s" % avail)
            if "active_liens" in df.columns:
                print("  Sum liens: %d" % df["active_liens"].sum())
            print("  First 3 owners:")
            for _, r in df.head(3).iterrows():
                print("    %-35s liens=%s" % (r.get("Owner","?")[:35], r.get("active_liens","?")))
    except Exception as e:
        print("%s: ERROR: %s" % (name, e))
        import traceback
        traceback.print_exc()
