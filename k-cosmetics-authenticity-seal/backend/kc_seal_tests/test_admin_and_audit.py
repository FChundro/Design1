import json
from pathlib import Path

from fastapi.testclient import TestClient
from kc_seal.config import Settings
from kc_seal.crypto import verify_envelope
from kc_seal.seed import TEST_REVOKED, TEST_VERIFIED

from kc_seal_tests.helpers import nonce

NEW_RECORD = {
    "is_test": True,
    "product_sku": "TEST-SKU-0099",
    "product_title": "TEST RECORD - Admin API demo",
    "manufacturer_batch": "TESTBATCH-9999",
    "supplier": {
        "supplier_id": "TEST-SUP-002",
        "supplier_name": "TEST Supplier B",
        "approval_status": "approved",
    },
    "evidence": [
        {
            "evidence_id": "TEST-EV-1",
            "type": "certificate_of_analysis",
            "reference": "TEST/COA/1",
            "sha256": "a" * 64,
            "received_on": "2026-11-01",
        }
    ],
}


def status_of(client: TestClient, seal_id: str) -> str:
    env = client.get(
        "/api/v1/heartbeat", params={"seal_id": seal_id, "nonce": nonce()}
    ).json()
    return verify_envelope(env, client.get("/api/v1/keys").json()["keys"])["status"]


def test_admin_requires_token(client: TestClient) -> None:
    assert client.post("/api/v1/admin/records", json=NEW_RECORD).status_code == 401
    assert (
        client.post(
            "/api/v1/admin/records",
            json=NEW_RECORD,
            headers={"Authorization": "Bearer wrong"},
        ).status_code
        == 401
    )
    assert client.get(f"/api/v1/admin/records/{TEST_VERIFIED}").status_code == 401


def test_create_generates_unguessable_id(
    client: TestClient, admin: dict[str, str]
) -> None:
    r = client.post("/api/v1/admin/records", json=NEW_RECORD, headers=admin)
    assert r.status_code == 201
    sid = r.json()["seal_id"]
    assert sid.startswith("KC-") and "TEST" not in sid[3:7]
    assert status_of(client, sid) == "verified_record"


def test_unknown_fields_rejected(client: TestClient, admin: dict[str, str]) -> None:
    bad = {**NEW_RECORD, "seal_id": "KC-AAAA-AAAA-AAAA-AAAA-AAAA-AAAA"}
    assert (
        client.post("/api/v1/admin/records", json=bad, headers=admin).status_code == 422
    )


def test_suspend_reinstate_revoke_lifecycle(
    client: TestClient, admin: dict[str, str]
) -> None:
    sid = client.post("/api/v1/admin/records", json=NEW_RECORD, headers=admin).json()[
        "seal_id"
    ]
    body = {"reason": "TEST: supplier query"}
    assert (
        client.post(
            f"/api/v1/admin/records/{sid}/suspend", json=body, headers=admin
        ).status_code
        == 200
    )
    assert status_of(client, sid) == "verification_suspended"
    assert (
        client.post(
            f"/api/v1/admin/records/{sid}/reinstate", json=body, headers=admin
        ).status_code
        == 200
    )
    assert status_of(client, sid) == "verified_record"
    assert (
        client.post(
            f"/api/v1/admin/records/{sid}/revoke", json=body, headers=admin
        ).status_code
        == 200
    )
    assert status_of(client, sid) == "verification_suspended"
    # revocation is permanent
    assert (
        client.post(
            f"/api/v1/admin/records/{sid}/reinstate", json=body, headers=admin
        ).status_code
        == 409
    )
    rec = client.get(f"/api/v1/admin/records/{sid}", headers=admin).json()
    assert [h["status"] for h in rec["history"]] == [
        "active",
        "suspended",
        "active",
        "revoked",
    ]


def test_revoked_seed_cannot_be_reinstated(
    client: TestClient, admin: dict[str, str]
) -> None:
    r = client.post(
        f"/api/v1/admin/records/{TEST_REVOKED}/reinstate",
        json={"reason": "TEST attempt"},
        headers=admin,
    )
    assert r.status_code == 409


def test_audit_chain_valid_and_signed(
    client: TestClient, admin: dict[str, str]
) -> None:
    client.post(
        f"/api/v1/admin/records/{TEST_VERIFIED}/suspend",
        json={"reason": "TEST audit"},
        headers=admin,
    )
    res = client.get("/api/v1/admin/audit/verify", headers=admin).json()
    assert res["ok"] is True and res["entries"] >= 5
    head = verify_envelope(
        res["signed_head"], client.get("/api/v1/keys").json()["keys"]
    )
    assert head["hash"] == res["head"]


def test_audit_tamper_detected(
    client: TestClient, admin: dict[str, str], settings: Settings
) -> None:
    client.post(
        f"/api/v1/admin/records/{TEST_VERIFIED}/suspend",
        json={"reason": "TEST tamper"},
        headers=admin,
    )
    path: Path = settings.data_dir / "audit" / "audit.jsonl"
    lines = path.read_text().splitlines()
    entry = json.loads(lines[2])
    entry["actor"] = "someone-else"
    lines[2] = json.dumps(entry)
    path.write_text("\n".join(lines) + "\n")
    res = client.get("/api/v1/admin/audit/verify", headers=admin).json()
    assert res["ok"] is False and res["broken_at_line"] == 3


def test_failed_admin_auth_is_audited(client: TestClient, settings: Settings) -> None:
    client.get(
        f"/api/v1/admin/records/{TEST_VERIFIED}",
        headers={"Authorization": "Bearer nope"},
    )
    log = (settings.data_dir / "audit" / "audit.jsonl").read_text()
    assert "admin_auth_failed" in log
    assert "nope" not in log
