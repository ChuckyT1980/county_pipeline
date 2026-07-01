import time
import requests
from .models import WorkUnit
from connectors.tehama import TehamaConnector
from meta_layer import MetaLayer0
from resolver import FieldResolver, MergeEngine
from completeness import CompletenessScorer
from scoring import UncertaintyAwareScorer
from counterfactual import CounterfactualEngine
from export_engine import generate_aplus_export, generate_crm_export

# Lazily initialized singletons for downstream systems
meta_layer = MetaLayer0()
resolver = FieldResolver()
merger = MergeEngine(resolver)
completeness = CompletenessScorer()
scorer = UncertaintyAwareScorer(completeness)
counterfactual = CounterfactualEngine(scorer)

from scheduler.replay_cache import DependencyFreeze

def get_connector(county: str):
    if county.lower() == "tehama":
        from connectors.tehama import TehamaConnector
        return TehamaConnector(county)
    if county.lower() == "shasta":
        from connectors.shasta import ShastaConnector
        return ShastaConnector(county)
    raise ValueError(f"Unknown connector for {county}")

def dispatch_batch(run_id: str, work_unit: WorkUnit, rps: float, distress_events_map: dict):
    connector = get_connector(work_unit.county)
    freeze = DependencyFreeze(run_id)
    delay = 1.0 / rps if rps > 0 else 1.0
    
    success_count = 0
    total_time = 0
    
    for apn in work_unit.apn_batch:
        start = time.time()
        
        event = distress_events_map.get(apn, {
            "apn": apn,
            "source": "tax_delinquency_notice",
            "amount_due": 5000.0,
            "default_year": 2021,
            "raw_owner_signal": ""
        })
        
        try:
            # 1. Fetch (with basic timeout hardening built into connector)
            identity_payload = connector.fetch_identity(apn)
            freeze.record(apn, "identity", identity_payload)
            
            snapshot_payload = connector.fetch_snapshot(apn)
            freeze.record(apn, "snapshot", snapshot_payload)
            
            # 2. Normalize
            norm_id = meta_layer.normalize(identity_payload.data, identity_payload.county)
            norm_snap = meta_layer.normalize(snapshot_payload.data, snapshot_payload.county)
            
            # 3. Resolve
            merged = merger.merge(
                (norm_id, identity_payload.source),
                (norm_snap, snapshot_payload.source)
            )
            
            # 4. Score
            score_data = scorer.score(merged, event)
            
            # 5. Counterfactual Optimization
            cf_result = counterfactual.analyze(merged, event, score_data["final_score"])
            
            # 6. Export (appending to CSV for now)
            lead_bundle = {
                "apn": apn,
                "merged_record": merged,
                "score_data": score_data,
                "distress_event": event,
                "counterfactual": cf_result.__dict__
            }
            
            # In a true distributed system, this export goes to a database
            # For now, we reuse our CRM generator but pass it as a singleton list
            df = generate_aplus_export([lead_bundle], f"A_PLUS_{work_unit.county.upper()}_PROBABILISTIC_{run_id}.csv")
            generate_crm_export(df, f"A_PLUS_{work_unit.county.upper()}_CRM_{run_id}.csv")
            
            success_count += 1
            
        except requests.exceptions.RequestException as e:
            print(f"[WORKER ERROR] Network failure for {apn}: {e}")
            # Scheduler will handle retry logic by not marking complete if we return failures
        except Exception as e:
            print(f"[WORKER ERROR] Processing failure for {apn}: {e}")
            
        total_time += (time.time() - start)
        time.sleep(delay)
        
    avg_latency = (total_time / len(work_unit.apn_batch) * 1000) if work_unit.apn_batch else 0
    success_rate = success_count / len(work_unit.apn_batch) if work_unit.apn_batch else 0
    
    return success_count, success_rate, avg_latency
