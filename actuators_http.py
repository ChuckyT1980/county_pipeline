import requests
import time
from actuators_schemas import ActuatorRequest, ActuatorResponse, ActuatorType, ActuatorError, ErrorType

class HTTPActuator:
    """
    Pure requests wrapper (DDL-1).
    NO implicit retries. NO heuristic parsing. NO connection reuse across steps.
    """
    def execute(self, req: ActuatorRequest) -> ActuatorResponse:
        start_time = time.time()
        
        try:
            # We strictly enforce the timeout requested by EER-1
            timeout_sec = req.timeout_ms / 1000.0
            
            # DDL-1: Instantiate strict, fresh session per execution step.
            # No connection pooling across steps. No implicit retries.
            from requests.adapters import HTTPAdapter
            import urllib3
            
            session = requests.Session()
            retry_strategy = urllib3.Retry(total=0, connect=0, read=0, status=0, redirect=0)
            adapter = HTTPAdapter(max_retries=retry_strategy)
            session.mount("http://", adapter)
            session.mount("https://", adapter)
            
            # The actuator blindly fires the request via the isolated session.
            response = session.request(
                method=req.method,
                url=req.url,
                headers=req.headers,
                data=req.payload,
                timeout=timeout_sec,
                allow_redirects=False # Determinism: Do not auto-follow redirects unless VPR requested it
            )
            
            # DDL-1: Immediately destroy session
            session.close()
            
            duration_ms = int((time.time() - start_time) * 1000)
            
            success = 200 <= response.status_code < 400
            
            error = None
            if response.status_code in [403, 401]:
                error = ActuatorError(ErrorType.WAF_BLOCK, f"HTTP {response.status_code}", ActuatorType.HTTP, False)
                
            return ActuatorResponse(
                execution_id=req.execution_id,
                step_id=req.step_id,
                actuator_type=ActuatorType.HTTP,
                status=response.status_code,
                success=success,
                raw_body=response.text,
                final_url=response.url,
                headers=dict(response.headers),
                timing_ms=duration_ms,
                artifacts={},
                error=error
            )
            
        except requests.exceptions.Timeout as e:
            duration_ms = int((time.time() - start_time) * 1000)
            return self._build_fail(req, ErrorType.TIMEOUT, str(e), duration_ms)
        except requests.exceptions.ConnectionError as e:
            duration_ms = int((time.time() - start_time) * 1000)
            return self._build_fail(req, ErrorType.NETWORK_ERROR, str(e), duration_ms)
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            return self._build_fail(req, ErrorType.UNKNOWN, str(e), duration_ms)

    def _build_fail(self, req: ActuatorRequest, err_type: ErrorType, msg: str, timing_ms: int) -> ActuatorResponse:
        return ActuatorResponse(
            execution_id=req.execution_id,
            step_id=req.step_id,
            actuator_type=ActuatorType.HTTP,
            status=None,
            success=False,
            raw_body="",
            final_url=req.url,
            headers={},
            timing_ms=timing_ms,
            artifacts={},
            error=ActuatorError(err_type, msg, ActuatorType.HTTP, False)
        )
