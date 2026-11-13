"""Shopify App Proxy request verification.

In production the verification page calls ``https://<official domain>/apps/kc-seal/heartbeat``.
Shopify forwards that request to this backend and appends ``shop``,
``timestamp``, ``path_prefix`` and an HMAC-SHA256 ``signature`` computed with
the custom app's secret. Verifying it proves the request came through the
official storefront domain, and lets us firewall the backend to Shopify only.

Algorithm (Shopify docs, "Authenticate app proxies"): remove ``signature``,
sort the remaining parameters, join each as ``key=value`` (multiple values
joined by ","), concatenate with no separator, HMAC-SHA256 with the app
secret, hex-encode, constant-time compare.
"""

import hashlib
import hmac
import time
from collections.abc import Iterable


def compute_signature(params: Iterable[tuple[str, object]], secret: str) -> str:
    grouped: dict[str, list[str]] = {}
    for key, value in params:
        if key == "signature":
            continue
        grouped.setdefault(key, []).append(str(value))
    message = "".join(f"{k}={','.join(v)}" for k, v in sorted(grouped.items()))
    return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()


def verify(
    params: list[tuple[str, str]],
    secret: str,
    *,
    max_skew_s: int = 300,
    now: float | None = None,
) -> bool:
    provided = next((v for k, v in params if k == "signature"), None)
    timestamp = next((v for k, v in params if k == "timestamp"), None)
    if not provided or not timestamp or not timestamp.isdigit():
        return False
    if abs((now or time.time()) - int(timestamp)) > max_skew_s:
        return False
    return hmac.compare_digest(compute_signature(params, secret), provided)
