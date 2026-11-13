"""Clearly labelled TEST records for the prototype and demonstration.

These seal IDs are deliberately recognisable (they contain "TEST"). Real seal
IDs are generated randomly by the server (120 bits) and are never guessable.
None of these records describe a real product, batch or supplier.
"""

import hashlib
from datetime import date
from typing import Literal

from .audit import AuditLog
from .models import EvidenceItem, LogisticsLink, RecordCreate, SupplierApproval
from .store import RecordStore

TEST_VERIFIED = "KC-TEST-VERI-FIED-AAAA-AAAA-AAA2"
TEST_SUSPENDED = "KC-TEST-SUSP-ENDE-DAAA-AAAA-AAA3"
TEST_REVOKED = "KC-TEST-REVO-KEDA-AAAA-AAAA-AAA4"
TEST_SUPPLIER_PENDING = "KC-TEST-PEND-INGA-AAAA-AAAA-AAA5"


def _doc_hash(label: str) -> str:
    return hashlib.sha256(f"TEST DOCUMENT {label}".encode()).hexdigest()


def _record(
    title: str,
    sku: str,
    batch: str,
    supplier_status: Literal["approved", "pending", "withdrawn"],
) -> RecordCreate:
    return RecordCreate(
        is_test=True,
        product_sku=sku,
        product_title=f"TEST RECORD - {title}",
        manufacturer_batch=batch,
        manufactured_on=date(2026, 8, 14),
        best_before=date(2029, 8, 13),
        supplier=SupplierApproval(
            supplier_id="TEST-SUP-001",
            supplier_name="TEST Supplier Co. (fictitious)",
            approval_status=supplier_status,
            approved_on=date(2026, 10, 1) if supplier_status == "approved" else None,
            review_due=date(2027, 10, 1),
        ),
        evidence=[
            EvidenceItem(
                evidence_id="TEST-EV-INV-001",
                type="supplier_invoice",
                reference="TEST/INV/2026/0001",
                sha256=_doc_hash("invoice"),
                received_on=date(2026, 10, 2),
            ),
            EvidenceItem(
                evidence_id="TEST-EV-ADL-001",
                type="authorised_distributor_letter",
                reference="TEST/ADL/2026/0001",
                sha256=_doc_hash("distributor letter"),
                received_on=date(2026, 10, 2),
            ),
            EvidenceItem(
                evidence_id="TEST-EV-GRI-001",
                type="goods_receipt_inspection",
                reference="TEST/GRI/2026/0001",
                sha256=_doc_hash("goods receipt"),
                received_on=date(2026, 10, 9),
            ),
        ],
        logistics=LogisticsLink(integration_status="not_integrated"),
    )


def seed(store: RecordStore, audit: AuditLog) -> list[str]:
    created = []
    plan: list[tuple[str, RecordCreate, Literal["suspended", "revoked"] | None]] = [
        (
            TEST_VERIFIED,
            _record(
                "Demo Centella Ampoule 100 ml",
                "TEST-SKU-0001",
                "TESTBATCH-2608A",
                "approved",
            ),
            None,
        ),
        (
            TEST_SUSPENDED,
            _record(
                "Demo Hydrating Toner 200 ml",
                "TEST-SKU-0002",
                "TESTBATCH-2608B",
                "approved",
            ),
            "suspended",
        ),
        (
            TEST_REVOKED,
            _record(
                "Demo Barrier Essence 50 ml",
                "TEST-SKU-0003",
                "TESTBATCH-2608C",
                "approved",
            ),
            "revoked",
        ),
        (
            TEST_SUPPLIER_PENDING,
            _record(
                "Demo Cleansing Foam 150 ml",
                "TEST-SKU-0004",
                "TESTBATCH-2608D",
                "pending",
            ),
            None,
        ),
    ]
    for seal_id, data, final_status in plan:
        if store.get(seal_id):
            continue
        store.create(data, actor="seed", seal_id=seal_id)
        audit.append(
            actor="seed", action="record_created", seal_id=seal_id, is_test=True
        )
        if final_status:
            store.set_status(
                seal_id,
                final_status,
                reason=f"TEST: demonstrate {final_status} state",
                actor="seed",
            )
            audit.append(
                actor="seed",
                action=f"record_{final_status}",
                seal_id=seal_id,
                is_test=True,
            )
        created.append(seal_id)
    return created
