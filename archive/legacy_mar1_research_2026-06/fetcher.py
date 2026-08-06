import requests
import time
from typing import Dict, List, Tuple, Any
from aql1 import AcquisitionQualityLens

class BaselineFetcher:
    def __init__(self, tax_source_url: str, vendor_registry_entry: Dict[str, Any] = None):
        self.tax_source_url = tax_source_url
        self.aql = AcquisitionQualityLens(vendor_registry_entry)
        
    def fetch_apns(self, apns: List[str]) -> Tuple[int, Dict[str, str]]:
        """
        Attempts to fetch the list of APNs from the endpoint.
        Returns (successful_fetches, failure_modes_tally)
        """
        successes = 0
        failure_tally = {
            "ACCESS_BLOCKED": 0,
            "ACCESS_DENIED": 0,
            "NOT_FOUND": 0,
            "TIMEOUT": 0,
            "UNKNOWN": 0
        }
        
        # We don't want to actually hit the real endpoint 50 times if it blocks us instantly.
        # So if we get a 403 on the first request, we can assume the rest will 403 to save time,
        # but for the audit, we'll try a few to be sure. We'll cap at 5 real requests if failing.
        
        diagnostics = []
        consecutive_failures = 0
        
        for apn in apns:
            if consecutive_failures >= 3:
                # Fast fail the rest
                failure_tally["ACCESS_BLOCKED"] += 1
                diagnostics.append(self.aql.diagnose_failure(self.tax_source_url, 403, {}, exception_str="Cascading Fast Fail"))
                continue
                
            url = f"{self.tax_source_url}?FeeParcel={apn.replace('-','')}"
            headers = {"User-Agent": "python-requests/2.31.0"}
            
            try:
                resp = requests.get(url, headers=headers, timeout=5, verify=False)
                
                if resp.status_code == 200:
                    successes += 1
                    consecutive_failures = 0
                else:
                    consecutive_failures += 1
                    # AQL-1 INTERCEPTION
                    diag = self.aql.diagnose_failure(url, resp.status_code, dict(resp.headers), resp.text[:500])
                    diagnostics.append(diag)
                    
                    if resp.status_code == 403: failure_tally["ACCESS_BLOCKED"] += 1
                    elif resp.status_code == 401: failure_tally["ACCESS_DENIED"] += 1
                    elif resp.status_code == 404: failure_tally["NOT_FOUND"] += 1
                    elif resp.status_code == 429: failure_tally["ACCESS_BLOCKED"] += 1
                    else: failure_tally["UNKNOWN"] += 1
                    
            except requests.exceptions.Timeout:
                failure_tally["TIMEOUT"] += 1
                consecutive_failures += 1
                diagnostics.append(self.aql.diagnose_failure(url, 0, {}, exception_str="Timeout"))
            except Exception as e:
                consecutive_failures += 1
                exc_str = str(e)
                diagnostics.append(self.aql.diagnose_failure(url, 0, {}, exception_str=exc_str))
                
                if "11001" in exc_str or "NameResolutionError" in exc_str:
                    failure_tally["ACCESS_BLOCKED"] += 1
                else:
                    failure_tally["UNKNOWN"] += 1
                
            time.sleep(0.5)
            
        return successes, failure_tally, diagnostics
