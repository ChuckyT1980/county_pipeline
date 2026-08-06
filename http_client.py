"""
http_client.py — thin cookie-persistent httpx wrapper.

The contract's HttpClient/HttpResponse protocols only require .get()/.post()
and .status_code/.content/.text — httpx already satisfies both shapes, so
this module mostly sets sensible defaults:

  * cookies persist for the lifetime of the client (Tyler's disclaimer flow
    depends on session-cookie survival between the GET and POST of /web/user/disclaimer)
  * follow_redirects=True (Tyler POSTs commonly 302 to /searchResults)
  * a real browser UA — Tyler + MPTS both discriminate against default httpx
    or curl agents in ways that can quietly return placeholder responses
  * one place to add proxy / rate-limit / retry policy later

No retries or backoff wired yet by design: BaseAdapter.capture() persists the
raw response before any parsing, so a bad first response is inspectable —
retry policy is best added once we see the specific failure shapes.
"""
from __future__ import annotations

from typing import Optional

import httpx


DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0 Safari/537.36"
)


def build_http_client(
    base_url: str = "",
    timeout: float = 15.0,
    user_agent: str = DEFAULT_UA,
    extra_headers: Optional[dict] = None,
) -> httpx.Client:
    """Return an httpx.Client configured to look like a real browser session.
    The returned client persists cookies across requests, follows redirects,
    and carries the given UA on every call. Callers may still add per-request
    AJAX headers (which is what the Tyler adapter does on searchPost/results)."""
    headers = {"User-Agent": user_agent}
    if extra_headers:
        headers.update(extra_headers)
    return httpx.Client(
        base_url=base_url,
        timeout=timeout,
        headers=headers,
        follow_redirects=True,
    )
