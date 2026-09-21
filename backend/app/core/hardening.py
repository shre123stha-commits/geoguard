"""Security middleware (techspec §8; task 8.6).

* `BodySizeLimitMiddleware` – rejects requests whose declared or streamed body exceeds a cap
  (default 6 MiB: the 5 MiB GeoJSON upload limit plus JSON overhead) with 413 before any
  parsing happens.
* `SecurityHeadersMiddleware` – conservative headers on every response. The SPA is served
  separately (Vite / static host), so the API can afford a strict CSP.
"""

from __future__ import annotations

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.api.errors import error_body

DEFAULT_MAX_BODY = 6 * 1024 * 1024
# Reference-layer uploads (government boundary files) are legitimately larger (Phase 9).
LARGE_BODY_PATHS = ("/api/v1/reference-layers",)
LARGE_MAX_BODY = 25 * 1024 * 1024

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "geolocation=(), camera=(), microphone=()",
    "Cache-Control": "no-store",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
}
# Files (PDF/PNG) and the interactive docs need a slightly looser policy.
_FILE_CSP = "default-src 'none'; img-src 'self'; object-src 'self'; frame-ancestors 'self'"
_DOCS_CSP = (
    "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data: "
    "https://fastapi.tiangolo.com; frame-ancestors 'none'"
)


class BodySizeLimitMiddleware:
    def __init__(self, app: ASGIApp, max_bytes: int = DEFAULT_MAX_BODY) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers") or [])
        declared = headers.get(b"content-length")
        limit = self.max_bytes
        if any(scope.get("path", "").startswith(p) for p in LARGE_BODY_PATHS):
            limit = max(limit, LARGE_MAX_BODY)
        if declared is not None and declared.isdigit() and int(declared) > limit:
            await self._reject(scope, receive, send, limit)
            return
        received = 0
        too_large = False

        async def limited_receive() -> Message:
            nonlocal received, too_large
            msg = await receive()
            if msg["type"] == "http.request":
                received += len(msg.get("body", b""))
                if received > limit:
                    too_large = True
                    # stop feeding the app; it will see an empty end-of-body
                    return {"type": "http.request", "body": b"", "more_body": False}
            return msg

        async def guarded_send(msg: Message) -> None:
            if too_large and msg["type"] == "http.response.start":
                msg = {**msg, "status": 413}
            await send(msg)

        await self.app(scope, limited_receive, guarded_send)

    async def _reject(self, scope: Scope, receive: Receive, send: Send, limit: int) -> None:
        resp = JSONResponse(
            status_code=413,
            content=error_body(
                "payload_too_large",
                f"Request body exceeds {limit // (1024 * 1024)} MB",
            ),
        )
        await resp(scope, receive, send)


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path: str = scope.get("path", "")
        is_docs = path in ("/docs", "/redoc") or path.endswith("/openapi.json")
        is_file = "/files/" in path

        async def send_with_headers(msg: Message) -> None:
            if msg["type"] == "http.response.start":
                raw = list(msg.get("headers") or [])
                present = {k.lower() for k, _ in raw}
                for k, v in SECURITY_HEADERS.items():
                    kb = k.lower().encode()
                    if kb in present:
                        continue  # a route may set Cache-Control itself (files do)
                    if k == "Content-Security-Policy" and is_docs:
                        v = _DOCS_CSP
                    if k == "Content-Security-Policy" and is_file:
                        v = _FILE_CSP
                    if k == "X-Frame-Options" and is_file:
                        v = "SAMEORIGIN"  # PDFs may be shown in an iframe of the app itself
                    raw.append((kb, v.encode()))
                msg = {**msg, "headers": raw}
            await send(msg)

        await self.app(scope, receive, send_with_headers)
