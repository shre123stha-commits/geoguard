"""Security middleware (task 8.6): body cap, headers, opaque 500s."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.errors import register_error_handlers
from app.core.hardening import BodySizeLimitMiddleware, SecurityHeadersMiddleware


def _app(max_bytes: int = 100) -> TestClient:
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=max_bytes)
    register_error_handlers(app)

    @app.post("/echo")
    async def echo(body: dict) -> dict:  # type: ignore[type-arg]
        return {"n": len(body)}

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("secret sql text")

    @app.get("/api/v1/files/x.pdf")
    async def f() -> dict:  # type: ignore[type-arg]
        return {}

    return TestClient(app, raise_server_exceptions=False)


def test_declared_oversize_body_is_rejected_early() -> None:
    c = _app(100)
    r = c.post(
        "/echo", content=b"{" + b" " * 200 + b"}", headers={"content-type": "application/json"}
    )
    assert r.status_code == 413
    assert r.json()["error"]["code"] == "payload_too_large"
    assert c.post("/echo", json={"a": 1}).status_code == 200


def test_security_headers_present_and_route_cache_control_kept() -> None:
    c = _app()
    r = c.post("/echo", json={})
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["cache-control"] == "no-store"
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
    r = c.get("/api/v1/files/x.pdf")
    assert r.headers["x-frame-options"] == "SAMEORIGIN"


def test_unhandled_errors_are_opaque() -> None:
    r = _app().get("/boom")
    assert r.status_code == 500
    assert r.json() == {
        "error": {
            "code": "internal_error",
            "message": "Something went wrong on the server",
            "details": None,
        }
    }
    assert "secret" not in r.text
