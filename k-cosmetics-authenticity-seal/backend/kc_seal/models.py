"""Data model for verification records.

Designed to carry supplier approval, product SKU, manufacturer batch number,
supporting evidence and a future 3PL (third-party logistics) link. Only a
minimal, non-sensitive subset is ever returned to the public (see
``SealRecord.public_view``).
"""

import re
import secrets
from datetime import UTC, date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# 6 groups of 4 base32 characters = 120 bits of entropy: cannot be guessed or
# enumerated, so knowing what the seal *looks like* reveals nothing usable.
SEAL_ID_RE = re.compile(r"^KC-[A-Z2-7]{4}(?:-[A-Z2-7]{4}){5}$")
_B32 = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"

RecordStatus = Literal["active", "suspended", "revoked"]
PublicStatus = Literal["verified_record", "verification_suspended", "not_found"]


def new_seal_id() -> str:
    chars = "".join(secrets.choice(_B32) for _ in range(24))
    return "KC-" + "-".join(chars[i : i + 4] for i in range(0, 24, 4))


def utcnow() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SupplierApproval(_Strict):
    supplier_id: str = Field(min_length=2, max_length=64)
    supplier_name: str = Field(min_length=2, max_length=120)
    approval_status: Literal["approved", "pending", "withdrawn"]
    approved_on: date | None = None
    review_due: date | None = None
    approved_by_role: str = Field(default="Compliance Manager", max_length=64)


class EvidenceItem(_Strict):
    evidence_id: str = Field(min_length=2, max_length=64)
    type: Literal[
        "supplier_invoice",
        "authorised_distributor_letter",
        "certificate_of_analysis",
        "cpnp_notification",
        "import_customs_document",
        "goods_receipt_inspection",
        "other",
    ]
    reference: str = Field(
        min_length=1,
        max_length=200,
        description="Internal document reference, never a public URL",
    )
    sha256: str = Field(
        pattern=r"^[0-9a-f]{64}$",
        description="Hash of the stored document for integrity checks",
    )
    received_on: date
    verified_by_role: str = Field(default="Compliance Manager", max_length=64)


class LogisticsLink(_Strict):
    """Placeholder for future 3PL integration (warehouse lot traceability)."""

    integration_status: Literal["not_integrated", "pending", "synced"] = (
        "not_integrated"
    )
    provider: str | None = Field(default=None, max_length=80)
    provider_lot_ref: str | None = Field(default=None, max_length=80)
    warehouse_code: str | None = Field(default=None, max_length=40)
    received_into_stock_on: date | None = None
    last_synced_at: datetime | None = None


class StatusEvent(_Strict):
    at: datetime
    status: RecordStatus
    reason: str = Field(max_length=300)
    actor: str = Field(max_length=64)


class RecordCreate(_Strict):
    is_test: bool = True
    product_sku: str = Field(min_length=2, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")
    product_title: str = Field(min_length=2, max_length=160)
    manufacturer_batch: str = Field(
        min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._/-]+$"
    )
    manufactured_on: date | None = None
    best_before: date | None = None
    supplier: SupplierApproval
    evidence: list[EvidenceItem] = Field(default_factory=list, max_length=50)
    logistics: LogisticsLink = Field(default_factory=LogisticsLink)


class SealRecord(RecordCreate):
    seal_id: str
    status: RecordStatus = "active"
    status_reason: str = ""
    history: list[StatusEvent] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    version: int = 1

    @field_validator("seal_id")
    @classmethod
    def _seal_format(cls, v: str) -> str:
        if not SEAL_ID_RE.match(v):
            raise ValueError("invalid seal id format")
        return v

    def public_status(self) -> tuple[PublicStatus, str]:
        if self.status != "active":
            return "verification_suspended", f"record_{self.status}"
        if self.supplier.approval_status != "approved":
            return "verification_suspended", "supplier_approval_not_current"
        if self.supplier.review_due and self.supplier.review_due < utcnow().date():
            return "verification_suspended", "supplier_review_overdue"
        return "verified_record", "record_active"

    def public_view(self) -> dict[str, object]:
        """The ONLY record data that leaves the server. No supplier contacts,
        no evidence documents, no internal references, no customer data."""
        return {
            "is_test": self.is_test,
            "product_title": self.product_title,
            "product_sku": self.product_sku,
            "manufacturer_batch": self.manufacturer_batch,
            "best_before": self.best_before.isoformat() if self.best_before else None,
            "supplier_approval": self.supplier.approval_status,
            "supplier_approved_on": (
                self.supplier.approved_on.isoformat()
                if self.supplier.approved_on
                else None
            ),
            "evidence_on_file": len(self.evidence),
            "evidence_types": sorted({e.type for e in self.evidence}),
            "logistics_integration": self.logistics.integration_status,
            "record_updated_at": self.updated_at.isoformat(),
        }


class StatusChange(_Strict):
    reason: str = Field(min_length=3, max_length=300)
