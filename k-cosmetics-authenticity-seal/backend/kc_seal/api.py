"""HTTP API for the live heartbeat seal.

Public (read-only, rate limited, no cookies):
  GET  /api/v1/heartbeat?seal_id=..&nonce=..   signed status, polled every 60 s
  GET  /proxy/heartbeat                        same, via Shopify App Proxy (HMAC checked)
  GET  /api/v1/keys                            public verification keys (JWKS)
  GET  /api/v1/revocations                     signed revocation list
  GET  /healthz

Admin (bearer token, audited):
  POST /api/v1/admin/records                   create record
  GET  /api/v1/admin/records/{seal_id}         full record (incl. evidence metadata)
  POST /api/v1/admin/records/{seal_id}/suspend
  POST /api/v1/admin/records/{seal_id}/reinstate
  POST /api/v1/admin/records/{seal_id}/revoke  permanent
  GET  /api/v1/admin/audit/verify              check hash chain, signed head
  POST /api/v1/admin/demo/fault                demo mode only: simulate failures
"""

import asyncio
import hashlib
import hmac
import re
from datetime import timedelta
from pathlib import Path
from typing import Annotated, Any, Literal

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import app_proxy
from .audit import AuditLog
from .config import Settings
from .crypto import Signer, load_or_create_private_key
from .models import SEAL_ID_RE, RecordCreate, SealRecord, StatusChange, utcnow
from .privacy import AccessLog, Pseudonymiser, RateLimiter
from .store import RecordConflict, RecordStore

NONCE_RE = re.compile(r"^[A-Za-z0-9_-]{16,64}$")
PROJECT_ROOT = Path(__file__).resolve().parents[2]
MAX_ADMIN_BODY = 64 * 1024

FaultMode = Literal["none", "outage", "forged_signature", "stale_response"]


class FaultRequest(BaseModel):
    mode: FaultMode


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    key = load_or_create_private_key(
        settings.signing_key_path, allow_generate=settings.dev_generate_key
    )
    signer = Signer(key, settings.key_id)
    store = RecordStore(settings.data_dir / "records.json")
    audit = AuditLog(settings.data_dir / "audit" / "audit.jsonl")
    access = AccessLog(settings.data_dir / "access", settings.access_log_retention_days)
    pseudo = Pseudonymiser()
    public_limiter = RateLimiter(
        settings.rate_limit_per_minute, settings.rate_limit_burst
    )
    admin_limiter = RateLimiter(60, 30)

    app = FastAPI(
        title="K-Cosmetics EU Authenticity Seal (PROTOTYPE)",
        version="0.1.0-prototype",
        docs_url="/docs" if settings.demo_mode else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.demo_mode else None,
    )
    app.state.settings = settings
    app.state.store = store
    app.state.audit = audit
    app.state.fault = "none"

    if settings.allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.allowed_origins),
            allow_methods=["GET"],
            allow_headers=[],
            allow_credentials=False,
            max_age=600,
        )

    @app.middleware("http")
    async def security_headers(request: Request, call_next: Any) -> Response:
        if request.url.path.startswith("/api/v1/admin"):
            length = request.headers.get("content-length")
            if length and length.isdigit() and int(length) > MAX_ADMIN_BODY:
                return JSONResponse({"error": "payload_too_large"}, status_code=413)
        response: Response = await call_next(request)
        h = response.headers
        h["X-Content-Type-Options"] = "nosniff"
        h["Referrer-Policy"] = "no-referrer"
        h["X-Frame-Options"] = "DENY"
        h["Cross-Origin-Resource-Policy"] = "same-site"
        h["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), interest-cohort=()"
        )
        h["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        )
        if settings.official_origin.startswith("https://"):
            h["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        if request.url.path.startswith(("/api/", "/proxy/")):
            h["Cache-Control"] = "no-store"
        return response

    def client_id(request: Request) -> str:
        ip = request.client.host if request.client else "unknown"
        return pseudo.client_id(ip)

    def require_admin(request: Request) -> str:
        cid = client_id(request)
        if not admin_limiter.allow(cid):
            raise HTTPException(429, "too_many_requests")
        auth = request.headers.get("authorization", "")
        token = (
            auth.removeprefix("Bearer ").strip() if auth.startswith("Bearer ") else ""
        )
        expected = settings.admin_token_sha256
        if not expected or not token:
            audit.append(
                actor=f"client:{cid}", action="admin_auth_failed", reason="missing"
            )
            raise HTTPException(401, "unauthorised")
        digest = hashlib.sha256(token.encode()).hexdigest()
        if not hmac.compare_digest(digest, expected):
            audit.append(
                actor=f"client:{cid}", action="admin_auth_failed", reason="bad_token"
            )
            raise HTTPException(401, "unauthorised")
        return f"admin:{digest[:8]}"

    Admin = Annotated[str, Depends(require_admin)]

    def build_heartbeat(seal_id: str, nonce: str) -> dict[str, Any]:
        now = utcnow()
        if app.state.fault == "stale_response":
            now = now - timedelta(minutes=10)
        record = store.get(seal_id)
        if record is None:
            status, reason, view, is_test = (
                "not_found",
                "no_matching_record",
                None,
                None,
            )
        else:
            status, reason = record.public_status()
            view, is_test = record.public_view(), record.is_test
        return {
            "v": 1,
            "type": "kc.seal.heartbeat",
            "seal_id": seal_id,
            "status": status,
            "reason": reason,
            "record": view,
            "is_test": is_test,
            "nonce": nonce,
            "origin": settings.official_origin,
            "issued_at": now.isoformat(),
            "expires_at": (
                now + timedelta(seconds=settings.response_ttl_s)
            ).isoformat(),
            "interval_s": settings.heartbeat_interval_s,
            "environment": settings.environment,
            "scope": "digital_record_only",
        }

    async def heartbeat_response(
        request: Request, seal_id: str, nonce: str
    ) -> Response:
        cid = client_id(request)
        if not public_limiter.allow(cid):
            access.record(client=cid, seal_id="-", outcome="rate_limited")
            return JSONResponse(
                {"error": "too_many_requests"},
                status_code=429,
                headers={"Retry-After": "60"},
            )
        if not SEAL_ID_RE.match(seal_id) or not NONCE_RE.match(nonce):
            access.record(client=cid, seal_id="-", outcome="bad_request")
            return JSONResponse({"error": "invalid_request"}, status_code=400)
        if app.state.fault == "outage":
            return JSONResponse({"error": "service_unavailable"}, status_code=503)
        payload = build_heartbeat(seal_id, nonce)
        if app.state.fault == "forged_signature":
            envelope = Signer(Ed25519PrivateKey.generate(), settings.key_id).sign(
                payload
            )
        else:
            envelope = signer.sign(payload)
        access.record(client=cid, seal_id=seal_id, outcome=payload["status"])
        return JSONResponse(envelope)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "environment": settings.environment}

    @app.get("/api/v1/heartbeat")
    async def heartbeat(
        request: Request,
        seal_id: Annotated[str, Query(max_length=40)],
        nonce: Annotated[str, Query(max_length=64)],
    ) -> Response:
        if settings.require_app_proxy:
            return JSONResponse({"error": "use_official_domain"}, status_code=403)
        return await heartbeat_response(request, seal_id, nonce)

    @app.get("/proxy/heartbeat")
    async def proxy_heartbeat(request: Request) -> Response:
        params = list(request.query_params.multi_items())
        if not settings.app_proxy_secret or not app_proxy.verify(
            params, settings.app_proxy_secret
        ):
            return JSONResponse({"error": "invalid_proxy_signature"}, status_code=401)
        q = dict(params)
        return await heartbeat_response(
            request, q.get("seal_id", ""), q.get("nonce", "")
        )

    @app.get("/api/v1/keys")
    async def keys() -> dict[str, Any]:
        return {"keys": [signer.jwk]}

    @app.get("/api/v1/revocations")
    async def revocations() -> dict[str, str]:
        return signer.sign(
            {
                "type": "kc.seal.revocations",
                "issued_at": utcnow().isoformat(),
                "revoked_seal_ids": store.revoked_ids(),
                "revoked_key_ids": [],
            }
        )

    @app.post("/api/v1/admin/records", status_code=201)
    async def create_record(body: RecordCreate, actor: Admin) -> SealRecord:
        record = store.create(body, actor=actor)
        audit.append(
            actor=actor,
            action="record_created",
            seal_id=record.seal_id,
            sku=record.product_sku,
            batch=record.manufacturer_batch,
            is_test=record.is_test,
        )
        return record

    @app.get("/api/v1/admin/records/{seal_id}")
    async def get_record(seal_id: str, actor: Admin) -> SealRecord:
        record = store.get(seal_id)
        if record is None:
            raise HTTPException(404, "not_found")
        return record

    async def change_status(
        seal_id: str,
        status: Literal["active", "suspended", "revoked"],
        body: StatusChange,
        actor: str,
        action: str,
    ) -> SealRecord:
        try:
            record = store.set_status(seal_id, status, reason=body.reason, actor=actor)
        except KeyError:
            raise HTTPException(404, "not_found") from None
        except RecordConflict as exc:
            raise HTTPException(409, str(exc)) from None
        audit.append(
            actor=actor,
            action=action,
            seal_id=seal_id,
            reason=body.reason,
            version=record.version,
        )
        return record

    @app.post("/api/v1/admin/records/{seal_id}/suspend")
    async def suspend(seal_id: str, body: StatusChange, actor: Admin) -> SealRecord:
        return await change_status(
            seal_id, "suspended", body, actor, "record_suspended"
        )

    @app.post("/api/v1/admin/records/{seal_id}/reinstate")
    async def reinstate(seal_id: str, body: StatusChange, actor: Admin) -> SealRecord:
        return await change_status(seal_id, "active", body, actor, "record_reinstated")

    @app.post("/api/v1/admin/records/{seal_id}/revoke")
    async def revoke(seal_id: str, body: StatusChange, actor: Admin) -> SealRecord:
        return await change_status(seal_id, "revoked", body, actor, "record_revoked")

    @app.get("/api/v1/admin/audit/verify")
    async def audit_verify(actor: Admin) -> dict[str, Any]:
        result = await asyncio.to_thread(audit.verify_chain)
        result["signed_head"] = signer.sign(
            {"type": "kc.seal.audit_head", "at": utcnow().isoformat(), **audit.head}
        )
        return result

    if settings.demo_mode:

        @app.post("/api/v1/admin/demo/fault")
        async def set_fault(body: FaultRequest, actor: Admin) -> dict[str, str]:
            app.state.fault = body.mode
            audit.append(actor=actor, action="demo_fault_set", mode=body.mode)
            return {"fault": body.mode}

        app.mount(
            "/theme-assets",
            StaticFiles(directory=PROJECT_ROOT / "theme" / "assets"),
            name="theme-assets",
        )
        app.mount(
            "/demo",
            StaticFiles(directory=PROJECT_ROOT / "demo", html=True),
            name="demo",
        )

    audit.append(
        actor="system",
        action="service_started",
        key_id=settings.key_id,
        environment=settings.environment,
    )
    return app
