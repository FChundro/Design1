import os
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from kc_seal import app_proxy
from kc_seal.api import create_app
from kc_seal.config import Settings
from kc_seal.crypto import KeyError_, load_or_create_private_key, verify_envelope
from kc_seal.privacy import AccessLog
from kc_seal.seed import TEST_VERIFIED, seed

from kc_seal_tests.helpers import PROXY_SECRET, make_settings, nonce


def test_fault_outage_returns_503(client: TestClient, admin: dict[str, str]) -> None:
    assert (
        client.post(
            "/api/v1/admin/demo/fault", json={"mode": "outage"}, headers=admin
        ).status_code
        == 200
    )
    r = client.get(
        "/api/v1/heartbeat", params={"seal_id": TEST_VERIFIED, "nonce": nonce()}
    )
    assert r.status_code == 503
    client.post("/api/v1/admin/demo/fault", json={"mode": "none"}, headers=admin)
    assert (
        client.get(
            "/api/v1/heartbeat", params={"seal_id": TEST_VERIFIED, "nonce": nonce()}
        ).status_code
        == 200
    )


def test_fault_forged_signature_fails_verification(
    client: TestClient, admin: dict[str, str]
) -> None:
    client.post(
        "/api/v1/admin/demo/fault", json={"mode": "forged_signature"}, headers=admin
    )
    env = client.get(
        "/api/v1/heartbeat", params={"seal_id": TEST_VERIFIED, "nonce": nonce()}
    ).json()
    with pytest.raises(ValueError, match="bad signature"):
        verify_envelope(env, client.get("/api/v1/keys").json()["keys"])


def test_fault_requires_admin_and_demo_mode(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path, demo_mode=False))
    with TestClient(app) as c:
        assert c.post(
            "/api/v1/admin/demo/fault", json={"mode": "outage"}
        ).status_code in (404, 405)
        assert c.get("/demo/index.html").status_code == 404
        assert c.get("/docs").status_code == 404


def test_rate_limit(tmp_path: Path) -> None:
    app = create_app(
        make_settings(tmp_path, rate_limit_per_minute=5, rate_limit_burst=3)
    )
    seed(app.state.store, app.state.audit)
    with TestClient(app) as c:
        codes = [
            c.get(
                "/api/v1/heartbeat", params={"seal_id": TEST_VERIFIED, "nonce": nonce()}
            ).status_code
            for _ in range(6)
        ]
    assert codes[:3] == [200, 200, 200]
    assert 429 in codes[3:]


def test_access_log_has_no_raw_ip(client: TestClient, settings: Settings) -> None:
    client.get("/api/v1/heartbeat", params={"seal_id": TEST_VERIFIED, "nonce": nonce()})
    logs = "".join(
        p.read_text() for p in (settings.data_dir / "access").glob("*.jsonl")
    )
    assert "testclient" not in logs and "127.0.0.1" not in logs
    assert '"client": "' in logs


def test_access_log_retention_purge(tmp_path: Path) -> None:
    log = AccessLog(tmp_path, retention_days=30)
    old = tmp_path / f"access-{(datetime.now(UTC) - timedelta(days=45)):%Y-%m-%d}.jsonl"
    old.write_text("{}\n")
    log.record(client="abc", seal_id="x", outcome="verified_record")
    removed = log.purge()
    assert old.name in removed and not old.exists()
    assert list(tmp_path.glob("access-*.jsonl"))


def test_signing_key_permissions_enforced(tmp_path: Path) -> None:
    key_path = tmp_path / "k.pem"
    load_or_create_private_key(key_path, allow_generate=True)
    assert (key_path.stat().st_mode & 0o777) == 0o600
    os.chmod(key_path, 0o644)
    with pytest.raises(KeyError_):
        load_or_create_private_key(key_path, allow_generate=False)


def test_missing_key_refuses_to_start_in_production(tmp_path: Path) -> None:
    with pytest.raises(KeyError_):
        create_app(make_settings(tmp_path, dev_generate_key=False))


def test_private_key_never_exposed(client: TestClient) -> None:
    body = client.get("/api/v1/keys").text
    assert "PRIVATE" not in body and '"d"' not in body


def _proxy_params(
    secret: str, **extra: str
) -> list[tuple[str, str | int | float | None]]:
    params: list[tuple[str, str | int | float | None]] = [
        ("shop", "k-cosmetics-eu.myshopify.com"),
        ("path_prefix", "/apps/kc-seal"),
        ("timestamp", str(int(time.time()))),
        *extra.items(),
    ]
    return [*params, ("signature", app_proxy.compute_signature(params, secret))]


def test_app_proxy_signature(client: TestClient) -> None:
    params = _proxy_params(PROXY_SECRET, seal_id=TEST_VERIFIED, nonce=nonce())
    assert client.get("/proxy/heartbeat", params=params).status_code == 200
    bad = _proxy_params("wrong_secret", seal_id=TEST_VERIFIED, nonce=nonce())
    assert client.get("/proxy/heartbeat", params=bad).status_code == 401
    old: list[tuple[str, str | int | float | None]] = [
        ("timestamp", "1000"),
        ("seal_id", TEST_VERIFIED),
    ]
    old.append(("signature", app_proxy.compute_signature(old, PROXY_SECRET)))
    assert client.get("/proxy/heartbeat", params=old).status_code == 401


def test_direct_endpoint_closed_when_proxy_required(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path, require_app_proxy=True))
    with TestClient(app) as c:
        r = c.get(
            "/api/v1/heartbeat", params={"seal_id": TEST_VERIFIED, "nonce": nonce()}
        )
        assert r.status_code == 403


def test_records_persist_across_restart(tmp_path: Path) -> None:
    s = make_settings(tmp_path)
    app = create_app(s)
    seed(app.state.store, app.state.audit)
    app2 = create_app(s)
    rec = app2.state.store.get(TEST_VERIFIED)
    assert rec is not None and rec.is_test
    assert app2.state.audit.verify_chain()["ok"]
