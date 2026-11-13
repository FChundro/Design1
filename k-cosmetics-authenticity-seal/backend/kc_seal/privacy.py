"""Privacy safeguards and abuse protection for public look-ups.

* No cookies, no accounts, no customer data.
* Raw IP addresses are never written to disk. A client is represented by
  HMAC-SHA256(daily_salt, ip) truncated to 16 hex characters. The salt
  rotates every UTC day and old salts are discarded, so identifiers cannot be
  linked across days or reversed (GDPR Art. 25/32 data minimisation).
* User-Agent and Referer are not stored.
* Access-log files are deleted after ``retention_days`` (default 30).
"""

import hashlib
import hmac
import json
import secrets
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path


class Pseudonymiser:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._day = ""
        self._salt = b""

    def _current_salt(self) -> bytes:
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        with self._lock:
            if today != self._day:
                self._day, self._salt = (
                    today,
                    secrets.token_bytes(32),
                )  # previous salt is dropped
            return self._salt

    def client_id(self, ip: str) -> str:
        return hmac.new(self._current_salt(), ip.encode(), hashlib.sha256).hexdigest()[
            :16
        ]


class AccessLog:
    def __init__(self, directory: Path, retention_days: int) -> None:
        self._dir = directory
        self._retention = retention_days
        self._lock = threading.Lock()
        directory.mkdir(parents=True, exist_ok=True)

    def record(self, *, client: str, seal_id: str, outcome: str) -> None:
        now = datetime.now(UTC)
        line = json.dumps(
            {
                "ts": now.isoformat(timespec="seconds"),
                "client": client,
                "seal_id": seal_id,
                "outcome": outcome,
            }
        )
        with (
            self._lock,
            (self._dir / f"access-{now:%Y-%m-%d}.jsonl").open(
                "a", encoding="utf-8"
            ) as fh,
        ):
            fh.write(line + "\n")

    def purge(self, now: datetime | None = None) -> list[str]:
        cutoff = (now or datetime.now(UTC)) - timedelta(days=self._retention)
        removed = []
        for f in self._dir.glob("access-*.jsonl"):
            try:
                day = datetime.strptime(
                    f.stem.removeprefix("access-"), "%Y-%m-%d"
                ).replace(tzinfo=UTC)
            except ValueError:
                continue
            if day < cutoff:
                f.unlink()
                removed.append(f.name)
        return removed


class RateLimiter:
    """Token bucket per pseudonymous client. In production also enforced at
    the edge (Cloudflare / Cloud Armor) so abusive traffic never reaches the app."""

    def __init__(self, per_minute: int, burst: int) -> None:
        self._rate = per_minute / 60.0
        self._burst = float(burst)
        self._buckets: dict[str, tuple[float, float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            tokens, last = self._buckets.get(key, (self._burst, now))
            tokens = min(self._burst, tokens + (now - last) * self._rate)
            if tokens < 1.0:
                self._buckets[key] = (tokens, now)
                return False
            self._buckets[key] = (tokens - 1.0, now)
            if len(self._buckets) > 50_000:  # bound memory under attack
                self._buckets.clear()
            return True
