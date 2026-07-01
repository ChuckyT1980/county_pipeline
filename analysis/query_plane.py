import os
import json

class DriftQuery:
    def __init__(self, ledger_path: str, replays_dir: str):
        self.ledger_path = ledger_path
        self.replays_dir = replays_dir

    def _load_ledger(self):
        entries = []
        if os.path.exists(self.ledger_path):
            with open(self.ledger_path, "r") as f:
                for line in f:
                    entries.append(json.loads(line))
        return entries

    def _load_report(self, run_id: str):
        path = os.path.join(self.replays_dir, run_id, "drift_report.json")
        if not os.path.exists(path):
            return {}
        with open(path, "r") as f:
            return json.load(f)

    def over_time(self, metric: str):
        """Returns time-series data for a specific drift metric."""
        entries = self._load_ledger()
        result = []
        for entry in entries:
            val = entry.get("drift_summary", {}).get(metric, 0)
            result.append({"run_id": entry["run_id"], metric: val})
        return result

    def by_field(self, field: str):
        """Aggregate drift types for a specific field across all available reports."""
        entries = self._load_ledger()
        result = {}
        for entry in entries:
            run_id = entry["run_id"]
            report = self._load_report(run_id)
            for event in report.get("drift_events", []):
                if event["field"] == field:
                    dtype = event["drift_type"]
                    result[dtype] = result.get(dtype, 0) + 1
        return {field: result}

    def composition(self, run_id: str):
        """Returns normalized drift ratios for a specific run."""
        report = self._load_report(run_id)
        summary = report.get("drift_summary", {})
        total = sum(summary.values())
        if total == 0:
            return {k: 0.0 for k in summary}
        return {k: v / total for k, v in summary.items()}


class ReplayQuery:
    def __init__(self, replays_dir: str):
        self.replays_dir = replays_dir

    def _load_result(self, run_id: str):
        path = os.path.join(self.replays_dir, run_id, "replay_result.json")
        if not os.path.exists(path):
            raise FileNotFoundError(f"No replay result found for {run_id}")
        with open(path, "r") as f:
            return json.load(f)

    def mismatches(self, run_id: str):
        """Returns all mismatched rows for a run."""
        res = self._load_result(run_id)
        return res.get("mismatched_rows", [])

    def field_diff(self, run_id: str, field: str):
        """Returns all mismatches for a specific field in a run."""
        mismatches = self.mismatches(run_id)
        result = []
        for row in mismatches:
            for diff in row.get("field_diffs", []):
                if diff["field"] == field:
                    result.append({
                        "row_id": row["row_id"],
                        "expected": diff.get("expected"),
                        "actual": diff.get("actual")
                    })
        return result

    def validate(self, run_id: str):
        """Determinism validation shortcut."""
        res = self._load_result(run_id)
        return {
            "match_rate": res.get("match_rate"),
            "checksum": "PASS" if res.get("checksum_match") else "FAIL",
            "deterministic": res.get("match_rate") == 1.0 and res.get("checksum_match")
        }


class StabilityQuery:
    def __init__(self, replays_dir: str, ledger_path: str):
        self.replays_dir = replays_dir
        self.ledger_path = ledger_path
        
    def _load_ledger(self):
        entries = []
        if os.path.exists(self.ledger_path):
            with open(self.ledger_path, "r") as f:
                for line in f:
                    entries.append(json.loads(line))
        return entries

    def _load_evo(self, run_id: str):
        path = os.path.join(self.replays_dir, run_id, "drift_evolution_report.json")
        if not os.path.exists(path):
            return {}
        with open(path, "r") as f:
            return json.load(f)

    def trend(self, window: int = 10):
        """Returns the most recent trend and delta vector."""
        entries = self._load_ledger()
        if not entries:
            return {"trend": "UNKNOWN", "delta_vector": []}
            
        recent = entries[-window:] if window else entries
        last_run = recent[-1]["run_id"]
        evo = self._load_evo(last_run)
        
        return {
            "trend": evo.get("trend", "UNKNOWN"),
            "delta_vector": evo.get("delta", [])
        }

    def score(self):
        """Strict arithmetic score over the most recent run: 1 / (1 + total_drift)."""
        entries = self._load_ledger()
        if not entries:
            return 1.0
        total_drift = entries[-1].get("total_drift", 0)
        return 1.0 / (1.0 + total_drift)


class AnomalyQuery:
    def __init__(self, ledger_path: str):
        self.ledger_path = ledger_path

    def _load_ledger(self):
        entries = []
        if os.path.exists(self.ledger_path):
            with open(self.ledger_path, "r") as f:
                for line in f:
                    entries.append(json.loads(line))
        return entries

    def spikes(self, threshold: float = 2.0):
        """Flags runs where total_drift > threshold * average_total_drift."""
        entries = self._load_ledger()
        if not entries:
            return []
        
        drifts = [e.get("total_drift", 0) for e in entries]
        avg = sum(drifts) / len(drifts)
        
        spikes = []
        for e in entries:
            if e.get("total_drift", 0) > avg * threshold:
                spikes.append({
                    "run_id": e["run_id"],
                    "total_drift": e["total_drift"],
                    "avg_drift": avg
                })
        return spikes

    def regressions(self):
        """Drift increases after a previously stable period."""
        entries = self._load_ledger()
        if len(entries) < 2:
            return []
            
        regs = []
        for i in range(1, len(entries)):
            prev = entries[i-1].get("total_drift", 0)
            curr = entries[i].get("total_drift", 0)
            if prev == 0 and curr > 0:
                regs.append({
                    "run_id": entries[i]["run_id"],
                    "jump": curr - prev
                })
        return regs

    def outliers(self, metric: str = "TOTAL_DRIFT"):
        """Simple z-score outlier detection (|z| > 2)."""
        entries = self._load_ledger()
        if len(entries) < 2:
            return []
            
        vals = []
        for e in entries:
            if metric == "TOTAL_DRIFT":
                vals.append(e.get("total_drift", 0))
            else:
                vals.append(e.get("drift_summary", {}).get(metric, 0))
                
        mean = sum(vals) / len(vals)
        variance = sum((x - mean) ** 2 for x in vals) / len(vals)
        std = variance ** 0.5
        
        if std == 0:
            return []
            
        outliers = []
        for i, val in enumerate(vals):
            z = (val - mean) / std
            if abs(z) > 2.0:
                outliers.append({
                    "run_id": entries[i]["run_id"],
                    "metric": metric,
                    "value": val,
                    "z_score": z
                })
        return outliers


class SystemQuery:
    def health(self, run_id: str):
        from analysis.system_health import get_system_health
        # Use empty bounds for v1 (to avoid loading full ledger dynamically here)
        bounds = {}
        return get_system_health(run_id, bounds)

class QueryPlane:
    def __init__(self, replays_dir: str = "replays", ledger_path: str = "drift_ledger.jsonl"):
        self.drift = DriftQuery(ledger_path, replays_dir)
        self.replay = ReplayQuery(replays_dir)
        self.stability = StabilityQuery(replays_dir, ledger_path)
        self.anomalies = AnomalyQuery(ledger_path)
        self.system = SystemQuery()
