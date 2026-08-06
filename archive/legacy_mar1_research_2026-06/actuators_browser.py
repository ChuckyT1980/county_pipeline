import time
from actuators_schemas import ActuatorRequest, ActuatorResponse, ActuatorType, ActuatorError, ErrorType

class BrowserActuator:
    """
    Pure Playwright wrapper.
    NO "smart conditions", NO heuristic hunting, NO retries.
    """
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

    def _ensure_browser(self):
        # DDL-1: Always create a completely fresh browser and context per execution step.
        # Zero state leakage across steps.
        try:
            if not self.playwright:
                from playwright.sync_api import sync_playwright
                self.playwright = sync_playwright().start()
                self.browser = self.playwright.chromium.launch(headless=True)
            self.context = self.browser.new_context()
            self.page = self.context.new_page()
        except ImportError:
            pass # Playwright not installed in this environment
            
    def _destroy_context(self):
        # DDL-1: Immediately destroy context post-execution
        if self.page:
            self.page.close()
            self.page = None
        if self.context:
            self.context.close()
            self.context = None

    def execute(self, req: ActuatorRequest) -> ActuatorResponse:
        self._ensure_browser()
        start_time = time.time()
        
        if not self.page:
            return self._build_fail(req, ErrorType.UNKNOWN, "Playwright not installed or failed to initialize", 0)
            
        try:
            if req.method == "NAVIGATE":
                wait_strategy = req.metadata.get("wait_until", "domcontentloaded") if req.metadata else "domcontentloaded"
                res = self.page.goto(req.url, timeout=req.timeout_ms, wait_until=wait_strategy)
                status = res.status if res else None
                html = self.page.content()
                duration_ms = int((time.time() - start_time) * 1000)
                return self._build_success(req, status, html, self.page.url, duration_ms)
                
            elif req.method == "CLICK":
                if not req.selector:
                    return self._build_fail(req, ErrorType.UNKNOWN, "CLICK requires selector", 0)
                    
                # DDL-1: Absolute determinism. Do NOT use smart waiting. Force the click immediately.
                self.page.click(req.selector, timeout=req.timeout_ms, force=True, no_wait_after=True)
                html = self.page.content()
                duration_ms = int((time.time() - start_time) * 1000)
                return self._build_success(req, 200, html, self.page.url, duration_ms)
                
            elif req.method == "EXTRACT_HTML":
                html = self.page.content()
                duration_ms = int((time.time() - start_time) * 1000)
                return self._build_success(req, 200, html, self.page.url, duration_ms)
                
            else:
                return self._build_fail(req, ErrorType.UNKNOWN, f"Unsupported method: {req.method}", 0)
                
        except Exception as e:
            err_msg = str(e).lower()
            duration_ms = int((time.time() - start_time) * 1000)
            err_type = ErrorType.UNKNOWN
            if "timeout" in err_msg:
                err_type = ErrorType.TIMEOUT
            elif "selector" in err_msg or "not found" in err_msg:
                err_type = ErrorType.SELECTOR_NOT_FOUND
            elif "net::" in err_msg:
                err_type = ErrorType.NETWORK_ERROR
                
            return self._build_fail(req, err_type, str(e), duration_ms)
        finally:
            self._destroy_context()

    def _build_success(self, req: ActuatorRequest, status: int, body: str, url: str, timing: int) -> ActuatorResponse:
        return ActuatorResponse(
            execution_id=req.execution_id,
            step_id=req.step_id,
            actuator_type=ActuatorType.PLAYWRIGHT,
            status=status,
            success=True,
            raw_body=body,
            final_url=url,
            headers={},
            timing_ms=timing,
            artifacts={},
            error=None
        )

    def _build_fail(self, req: ActuatorRequest, err_type: ErrorType, msg: str, timing_ms: int) -> ActuatorResponse:
        return ActuatorResponse(
            execution_id=req.execution_id,
            step_id=req.step_id,
            actuator_type=ActuatorType.PLAYWRIGHT,
            status=None,
            success=False,
            raw_body="",
            final_url=req.url,
            headers={},
            timing_ms=timing_ms,
            artifacts={},
            error=ActuatorError(err_type, msg, ActuatorType.PLAYWRIGHT, False)
        )
