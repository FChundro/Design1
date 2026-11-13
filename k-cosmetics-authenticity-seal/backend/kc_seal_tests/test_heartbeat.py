from datetime import datetime, timedelta

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from kc_seal.crypto import Signer, b64url, b64url_decode, verify_envelope
from kc_seal.seed import (
    TEST_REVOKED,
    TEST_SUPPLIER_PENDING,
    TEST_SUSPENDED,
    TEST_VERIFIED,
)

from kc_seal_tests.helpers import nonce


def beat(client: TestClient, seal_id: str, n: str | None = None) -> tuple[dict, dict]:
    n = n or nonce()
    r = client.get("/api/v1/heartbeat", params={"seal_id": seal_id, "nonce": n})
    assert r.status_code == 200, r.text
    env = r.json()
    keys = client.get("/api/v1/keys").json()["keys"]
    payload = verify_envelope(env, keys)
    assert payload["nonce"] == n
    return env, payload


def test_verified_record_is_signed_and_fresh(client: TestClient) -> None:
    _, p = beat(client, TEST_VERIFIED)
    assert p["status"] == "verified_record"
    assert p["is_test"] is True
    assert p["record"]["product_title"].startswith("TEST RECORD")
    assert p["interval_s"] == 60
    assert p["scope"] == "digital_record_only"
    issued = datetime.fromisoformat(p["issued_at"])
    assert issued.utcoffset() == timedelta(0)


def test_three_statuses(client: TestClient) -> None:
    assert beat(client, TEST_SUSPENDED)[1]["status"] == "verification_suspended"
    assert beat(client, TEST_REVOKED)[1]["status"] == "verification_suspended"
    pending = beat(client, TEST_SUPPLIER_PENDING)[1]
    assert pending["status"] == "verification_suspended"
    assert pending["reason"] == "supplier_approval_not_current"
    unknown = beat(client, "KC-AAAA-BBBB-CCCC-DDDD-EEEE-FFFF")[1]
    assert unknown["status"] == "not_found" and unknown["record"] is None


def test_public_view_leaks_no_internal_data(client: TestClient) -> None:
    _, p = beat(client, TEST_VERIFIED)
    flat = repr(p)
    for secret_field in (
        "TEST/INV",
        "sha256",
        "supplier_name",
        "TEST-SUP-001",
        "history",
        "reference",
    ):
        assert secret_field not in flat
    assert p["record"]["evidence_on_file"] == 3


def test_each_response_bound_to_its_nonce(client: TestClient) -> None:
    env1, p1 = beat(client, TEST_VERIFIED)
    env2, p2 = beat(client, TEST_VERIFIED)
    assert p1["nonce"] != p2["nonce"]
    assert env1["sig"] != env2["sig"]


def test_tampered_payload_rejected(client: TestClient) -> None:
    env, _ = beat(client, TEST_SUSPENDED)
    keys = client.get("/api/v1/keys").json()["keys"]
    raw = b64url_decode(env["payload"]).replace(
        b"verification_suspended", b"verified_record"
    )
    forged = {**env, "payload": b64url(raw)}
    try:
        verify_envelope(forged, keys)
    except ValueError as exc:
        assert "bad signature" in str(exc)
    else:
        raise AssertionError("tampered payload accepted")


def test_copied_seal_cannot_mint_valid_response(client: TestClient) -> None:
    """A counterfeiter who copies the seal artwork and even the whole page markup
    still lacks the server's private key: any response they fabricate fails."""
    keys = client.get("/api/v1/keys").json()["keys"]
    fake = Signer(Ed25519PrivateKey.generate(), keys[0]["kid"]).sign(
        {
            "v": 1,
            "type": "kc.seal.heartbeat",
            "status": "verified_record",
            "seal_id": TEST_VERIFIED,
        }
    )
    try:
        verify_envelope(fake, keys)
    except ValueError:
        pass
    else:
        raise AssertionError("forged response accepted")


def test_input_validation(client: TestClient) -> None:
    for bad in [
        "",
        "KC-TEST",
        "kc-test-veri-fied-aaaa-aaaa-aaa2",
        "KC-0000-0000-0000-0000-0000-0000",
        "<script>",
    ]:
        r = client.get("/api/v1/heartbeat", params={"seal_id": bad, "nonce": nonce()})
        assert r.status_code in (400, 422)
    r = client.get(
        "/api/v1/heartbeat", params={"seal_id": TEST_VERIFIED, "nonce": "short"}
    )
    assert r.status_code == 400


def test_security_headers_and_no_cache(client: TestClient) -> None:
    r = client.get(
        "/api/v1/heartbeat", params={"seal_id": TEST_VERIFIED, "nonce": nonce()}
    )
    assert r.headers["cache-control"] == "no-store"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert "set-cookie" not in r.headers


def test_cors_only_for_official_origin(client: TestClient) -> None:
    ok = client.get(
        "/api/v1/heartbeat",
        params={"seal_id": TEST_VERIFIED, "nonce": nonce()},
        headers={"Origin": "http://testserver"},
    )
    assert ok.headers.get("access-control-allow-origin") == "http://testserver"
    evil = client.get(
        "/api/v1/heartbeat",
        params={"seal_id": TEST_VERIFIED, "nonce": nonce()},
        headers={"Origin": "https://k-cosmetics-fake.shop"},
    )
    assert "access-control-allow-origin" not in evil.headers


def test_revocation_list_signed(client: TestClient) -> None:
    keys = client.get("/api/v1/keys").json()["keys"]
    lst = verify_envelope(client.get("/api/v1/revocations").json(), keys)
    assert lst["revoked_seal_ids"] == [TEST_REVOKED]
