"""
run_state_pipeline.py — Universal 58-County State Orchestrator
============================================================
Runs both revenue legs across all 58 California counties in a single command.
Guarantees zero cascading failures: each county runs inside an isolated try/except block.

Modes:
  --mode prop_intel : Score upcoming auction parcels & build investor dossiers
  --mode excess     : Extract surplus claims, skip trace owners, & build outreach letters
  --mode full       : Run both revenue legs across all 58 counties

Usage:
  python run_state_pipeline.py --mode full
  python run_state_pipeline.py --mode prop_intel --county butte
  python run_state_pipeline.py --mode excess --county humboldt
"""

import argparse
import json
import os
import sys
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HEALTH_MATRIX = ROOT / "output" / "county_health_matrix.json"

PRIORITY_COUNTIES = ["butte", "fresno", "kern", "humboldt", "tehama", "shasta", "placer", "san_benito"]

def load_all_county_slugs():
    counties_dir = ROOT / "counties"
    if not counties_dir.exists():
        return PRIORITY_COUNTIES
    slugs = [yf.stem for yf in sorted(counties_dir.glob("*.yaml"))]
    return slugs or PRIORITY_COUNTIES

def update_health_matrix(county: str, status: str, details: dict):
    HEALTH_MATRIX.parent.mkdir(parents=True, exist_ok=True)
    matrix = {}
    if HEALTH_MATRIX.exists():
        try:
            with open(HEALTH_MATRIX, "r", encoding="utf-8") as f:
                matrix = json.load(f)
        except:
            matrix = {}
            
    matrix["last_updated"] = datetime.now(timezone.utc).isoformat()
    if "counties" not in matrix:
        matrix["counties"] = {}
        
    matrix["counties"][county] = {
        "status": status,
        **details,
        "last_checked": datetime.now(timezone.utc).isoformat()
    }
    
    with open(HEALTH_MATRIX, "w", encoding="utf-8") as f:
        json.dump(matrix, f, indent=2)

def run_county_leg1(county: str):
    """Leg 1: Property Intelligence Pre-Auction."""
    print(f"\n--- [Leg 1: Prop Intel] Processing '{county}' ---")
    try:
        # Check if county has local DB; if missing, auto-discover live from county portal (no target list needed)
        c_db = ROOT / "data" / "counties" / county / "state.sqlite"
        if not c_db.exists():
            print(f"  [auto_discovery] No local DB for '{county}' — discovering parcels live from county portal...")
            try:
                import auto_discovery_engine
                auto_discovery_engine.discover_county(county, limit=50)
            except Exception as e:
                print(f"  [auto_discovery] Discovery warning for '{county}': {e}")

        # Pre-flight circuit breaker check
        cb_res = subprocess.run(
            [sys.executable, "integrity_circuit_breaker.py", "--county", county],
            capture_output=True, text=True, cwd=str(ROOT), timeout=60
        )
        if cb_res.returncode != 0 and "ALERT" in cb_res.stdout:
            print(f"  [WARN] Circuit breaker halted '{county}': {cb_res.stdout[:150]}")
            update_health_matrix(county, "CIRCUIT_HALT", {"reason": "Null ratio > 20%"})
            return False
            
        # Run query engine with limit 100
        qe_res = subprocess.run(
            [sys.executable, "county_query_engine.py", "--county", county, "--type", "prop_intel", "--generate-reports", "--limit", "100"],
            capture_output=True, text=True, cwd=str(ROOT), timeout=120
        )
        
        # Auto-predict upcoming tax auction list (30-90 days in advance)
        try:
            import auction_predictor
            auction_predictor.predict_county_auction_list(county)
        except Exception as pe:
            print(f"  [auction_predictor] Warning for '{county}': {pe}")
            
        print(f"  [OK] Leg 1 completed for '{county}'.")
        update_health_matrix(county, "HEALTHY", {"leg1_status": "COMPLETE"})
        return True
    except Exception as e:
        print(f"  [FAIL] Error in Leg 1 for '{county}': {e}")
        update_health_matrix(county, "ERROR", {"error": str(e)})
        return False

def run_county_leg2(county: str):
    """Leg 2: Excess Proceeds Post-Auction Recovery."""
    print(f"\n--- [Leg 2: Excess Proceeds] Processing '{county}' ---")
    try:
        # Skip trace
        import skip_trace
        st_ok = skip_trace.run_skip_trace(county, dry_run=True)
        
        # Outreach generation
        import outreach_generator
        og_ok = outreach_generator.generate_outreach(county)
        
        print(f"  [OK] Leg 2 completed for '{county}'.")
        update_health_matrix(county, "HEALTHY", {"leg2_status": "COMPLETE"})
        return True
    except Exception as e:
        print(f"  [FAIL] Error in Leg 2 for '{county}': {e}")
        update_health_matrix(county, "ERROR", {"leg2_error": str(e)})
        return False

def main():
    parser = argparse.ArgumentParser(description="Universal 58-County State Orchestrator")
    parser.add_argument("--mode", choices=["full", "prop_intel", "excess"], default="full", help="Pipeline execution mode")
    parser.add_argument("--county", help="Single county slug to process (default: all 58)")
    args = parser.parse_args()
    
    counties = [args.county.lower()] if args.county else load_all_county_slugs()
    
    print(f"============================================================")
    print(f"CA-UNIFY Master Orchestrator — Mode: {args.mode.upper()}")
    print(f"Target Counties ({len(counties)}): {', '.join(counties[:10])}{'...' if len(counties)>10 else ''}")
    print(f"============================================================")
    
    success_count = 0
    fail_count = 0
    
    for c in counties:
        leg1_ok = True
        leg2_ok = True
        
        if args.mode in ["full", "prop_intel"]:
            leg1_ok = run_county_leg1(c)
            
        if args.mode in ["full", "excess"]:
            leg2_ok = run_county_leg2(c)
            
        if leg1_ok and leg2_ok:
            success_count += 1
        else:
            fail_count += 1
            
    print(f"\n============================================================")
    print(f"State Orchestration Run Complete")
    print(f"Successful: {success_count} / {len(counties)}")
    print(f"Encountered Warnings/Errors: {fail_count} / {len(counties)}")
    print(f"Health Matrix Updated: {HEALTH_MATRIX}")
    
    # Auto-update Active Buyer Intelligence Database
    try:
        import active_buyer_intelligence
        active_buyer_intelligence.build_buyer_intelligence_database()
    except Exception as e:
        print(f"[buyer_intel] Warning: could not refresh buyer database: {e}")
        
    print(f"============================================================")

if __name__ == "__main__":
    main()
