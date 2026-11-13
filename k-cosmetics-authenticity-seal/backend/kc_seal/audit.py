"""Tamper-evident audit log.

Every administrative action (create, suspend, reinstate, revoke, key events,
fault injection) is appended to a hash-chained JSON Lines file: each entry
stores the SHA-256 of the previous entry, so editing or deleting any line
breaks the chain and is detected by ``verify_chain``. The chain head can be
signed with the server key and exported to WORM storage for anchoring.

Public verification look-ups are NOT written here; they go to the short-
retention, pseudonymised access log in ``privacy.py``.
"""

import hashlib
import json
import threading
from pathlib import Path
from typing import Any

from .crypto import canonical_json
from .models import utcnow

GENESIS = "0" * 64


class AuditLog:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()
        path.parent.mkdir(parents=True, exist_ok=True)
        self._seq, self._head = self._load_tail()

    def _load_tail(self) -> tuple[int, str]:
        if not self._path.exists():
            return 0, GENESIS
        last = None
        with self._path.open("r", encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    last = json.loads(line)
        if last is None:
            return 0, GENESIS
        return int(last["seq"]), str(last["hash"])

    @staticmethod
    def _hash(entry: dict[str, Any]) -> str:
        body = {k: v for k, v in entry.items() if k != "hash"}
        return hashlib.sha256(canonical_json(body)).hexdigest()

    def append(
        self, *, actor: str, action: str, seal_id: str | None = None, **details: Any
    ) -> dict[str, Any]:
        with self._lock:
            entry: dict[str, Any] = {
                "seq": self._seq + 1,
                "ts": utcnow().isoformat(),
                "actor": actor,
                "action": action,
                "seal_id": seal_id,
                "details": details,
                "prev_hash": self._head,
            }
            entry["hash"] = self._hash(entry)
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
                fh.flush()
            self._seq, self._head = entry["seq"], entry["hash"]
            return entry

    @property
    def head(self) -> dict[str, Any]:
        return {"seq": self._seq, "hash": self._head}

    def verify_chain(self) -> dict[str, Any]:
        prev, expected_seq, count = GENESIS, 1, 0
        if not self._path.exists():
            return {"ok": True, "entries": 0, "head": GENESIS}
        with self._path.open("r", encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, start=1):
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    return {
                        "ok": False,
                        "entries": count,
                        "broken_at_line": lineno,
                        "error": "unparseable",
                    }
                if entry.get("seq") != expected_seq or entry.get("prev_hash") != prev:
                    return {
                        "ok": False,
                        "entries": count,
                        "broken_at_line": lineno,
                        "error": "chain_break",
                    }
                if self._hash(entry) != entry.get("hash"):
                    return {
                        "ok": False,
                        "entries": count,
                        "broken_at_line": lineno,
                        "error": "hash_mismatch",
                    }
                prev, expected_seq, count = entry["hash"], expected_seq + 1, count + 1
        return {"ok": True, "entries": count, "head": prev}
