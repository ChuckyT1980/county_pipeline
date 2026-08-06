import requests
import time
import hashlib
from eer1_schemas import ExecutionResult, SessionContext, RuntimeFailureType, StepFailure
from vpr3 import ExecutionStep, StepType

class HTTPDispatcher:
    def __init__(self):
        # Strictly stateless wrapper unless session provided
        pass
        
    def execute(self, step: ExecutionStep, session: SessionContext) -> ExecutionResult:
        start_time = time.time()
        try:
            headers = {"User-Agent": "python-requests/EER-1"}
            headers.update(session.headers)
            
            # Simulated endpoints for testing local paths without full scraping
            url = step.target if step.target else "https://example.com"
            if url == "tax_source": url = "https://mptsweb.co.shasta.ca.us/search.asp"
            if url == "landing_page": url = "https://mptsweb.co.shasta.ca.us/landing"
            
            # Strict Execution (No explicit retries unless VPR3 says STRICT - but VPR3 only allows 1 retry identical req, we'll simulate basic block)
            resp = requests.get(url, headers=headers, cookies=session.cookies, timeout=step.timeout_ms/1000.0, verify=False)
            latency_ms = int((time.time() - start_time) * 1000)
            
            output_hash = hashlib.md5(resp.content).hexdigest()
            
            if resp.status_code >= 400:
                # EER-1 rule: soft failures (429) vs hard failures (403, 500)
                # But in EER-1, ALL failures are recorded. 
                return ExecutionResult(
                    step_id=step.id,
                    status="FAILURE",
                    response={"status_code": resp.status_code, "headers": dict(resp.headers)},
                    latency_ms=latency_ms,
                    error_type=RuntimeFailureType.HTTP_ERROR.value,
                    output_hash=output_hash
                )
                
            return ExecutionResult(
                step_id=step.id,
                status="SUCCESS",
                response={"status_code": resp.status_code, "text": resp.text[:200]},
                latency_ms=latency_ms,
                error_type=None,
                output_hash=output_hash
            )
            
        except requests.exceptions.Timeout:
            return ExecutionResult(
                step_id=step.id,
                status="FAILURE",
                response=None,
                latency_ms=int((time.time() - start_time) * 1000),
                error_type=RuntimeFailureType.STEP_TIMEOUT.value,
                output_hash=None
            )
        except requests.exceptions.RequestException as e:
            return ExecutionResult(
                step_id=step.id,
                status="FAILURE",
                response=None,
                latency_ms=int((time.time() - start_time) * 1000),
                error_type=RuntimeFailureType.NETWORK_ERROR.value,
                output_hash=None
            )

class BrowserDispatcher:
    def __init__(self):
        pass
        
    def execute(self, step: ExecutionStep, session: SessionContext) -> ExecutionResult:
        # Mocking browser behavior for Phase 2.13 validation
        start_time = time.time()
        
        # Simulate browser execution
        time.sleep(1)
        latency_ms = int((time.time() - start_time) * 1000)
        
        return ExecutionResult(
            step_id=step.id,
            status="SUCCESS",
            response={"dom_loaded": True},
            latency_ms=latency_ms,
            error_type=None,
            output_hash="browser_dom_hash_123"
        )
