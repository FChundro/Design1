"""Record storage.

Prototype: one JSON file written atomically under a lock. Production: the
same interface backed by managed PostgreSQL (see docs/TECHNICAL_PROPOSAL.md).
"""

import json
import os
import tempfile
import threading
from pathlib import Path

from .models import (
    RecordCreate,
    RecordStatus,
    SealRecord,
    StatusEvent,
    new_seal_id,
    utcnow,
)


class RecordConflict(RuntimeError):
    pass


class RecordStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.RLock()
        self._records: dict[str, SealRecord] = {}
        if path.exists():
            raw = json.loads(path.read_text("utf-8"))
            self._records = {
                r["seal_id"]: SealRecord.model_validate(r)
                for r in raw.get("records", [])
            }

    def _flush(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = {"records": [r.model_dump(mode="json") for r in self._records.values()]}
        fd, tmp = tempfile.mkstemp(
            dir=self._path.parent, prefix=".records.", suffix=".tmp"
        )
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
        os.replace(tmp, self._path)

    def get(self, seal_id: str) -> SealRecord | None:
        with self._lock:
            return self._records.get(seal_id)

    def all(self) -> list[SealRecord]:
        with self._lock:
            return list(self._records.values())

    def create(
        self, data: RecordCreate, *, actor: str, seal_id: str | None = None
    ) -> SealRecord:
        with self._lock:
            sid = seal_id or new_seal_id()
            if sid in self._records:
                raise RecordConflict("seal id already exists")
            now = utcnow()
            record = SealRecord(
                **data.model_dump(),
                seal_id=sid,
                created_at=now,
                updated_at=now,
                history=[
                    StatusEvent(
                        at=now, status="active", reason="record created", actor=actor
                    )
                ],
            )
            self._records[sid] = record
            self._flush()
            return record

    def set_status(
        self, seal_id: str, status: RecordStatus, *, reason: str, actor: str
    ) -> SealRecord:
        with self._lock:
            record = self._records.get(seal_id)
            if record is None:
                raise KeyError(seal_id)
            if record.status == "revoked":
                raise RecordConflict(
                    "revoked records are permanent and cannot change status"
                )
            if record.status == status:
                raise RecordConflict(f"record is already {status}")
            now = utcnow()
            updated = record.model_copy(
                update={
                    "status": status,
                    "status_reason": reason,
                    "updated_at": now,
                    "version": record.version + 1,
                    "history": [
                        *record.history,
                        StatusEvent(at=now, status=status, reason=reason, actor=actor),
                    ],
                }
            )
            self._records[seal_id] = updated
            self._flush()
            return updated

    def revoked_ids(self) -> list[str]:
        with self._lock:
            return sorted(
                r.seal_id for r in self._records.values() if r.status == "revoked"
            )
