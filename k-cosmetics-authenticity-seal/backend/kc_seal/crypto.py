"""Ed25519 signing of verification responses.

The private key lives only on the server (file with 0600 permissions in the
prototype; a cloud KMS / HSM key in production). Browsers receive only the
public key, pinned in the theme, and verify every heartbeat response.

Envelope format (what clients receive)::

    {"alg": "Ed25519", "kid": "...", "payload": "<base64url canonical JSON>",
     "sig": "<base64url signature over the payload bytes>"}

Signing the exact bytes, rather than re-serialising JSON on the client,
removes any canonicalisation ambiguity.
"""

import base64
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64url_decode(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def canonical_json(obj: Any) -> bytes:
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


class KeyError_(RuntimeError):
    """Raised when the signing key is missing or unusable."""


def load_or_create_private_key(
    path: Path, *, allow_generate: bool
) -> Ed25519PrivateKey:
    if path.exists():
        mode = path.stat().st_mode & 0o777
        if mode & 0o077:
            raise KeyError_(
                f"Signing key {path} must not be readable by group/others (mode {oct(mode)})"
            )
        key = serialization.load_pem_private_key(path.read_bytes(), password=None)
        if not isinstance(key, Ed25519PrivateKey):
            raise KeyError_("Signing key is not an Ed25519 key")
        return key
    if not allow_generate:
        raise KeyError_(
            f"Signing key not found at {path}; set KC_SEAL_DEV_GENERATE_KEY=1 only for local testing"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    key = Ed25519PrivateKey.generate()
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(pem)
    return key


def public_jwk(public_key: Ed25519PublicKey, kid: str) -> dict[str, str]:
    raw = public_key.public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    return {
        "kty": "OKP",
        "crv": "Ed25519",
        "x": b64url(raw),
        "kid": kid,
        "use": "sig",
        "alg": "Ed25519",
    }


@dataclass
class Signer:
    private_key: Ed25519PrivateKey
    kid: str

    def sign(self, payload: dict[str, Any]) -> dict[str, str]:
        data = canonical_json(payload)
        return {
            "alg": "Ed25519",
            "kid": self.kid,
            "payload": b64url(data),
            "sig": b64url(self.private_key.sign(data)),
        }

    @property
    def jwk(self) -> dict[str, str]:
        return public_jwk(self.private_key.public_key(), self.kid)


def verify_envelope(
    envelope: dict[str, str], jwks: list[dict[str, str]]
) -> dict[str, Any]:
    """Reference verifier (mirrors the browser logic). Raises ValueError on failure."""
    if envelope.get("alg") != "Ed25519":
        raise ValueError("unsupported alg")
    key = next((k for k in jwks if k.get("kid") == envelope.get("kid")), None)
    if key is None:
        raise ValueError("unknown kid")
    pub = Ed25519PublicKey.from_public_bytes(b64url_decode(key["x"]))
    data = b64url_decode(envelope["payload"])
    try:
        pub.verify(b64url_decode(envelope["sig"]), data)
    except InvalidSignature as exc:
        raise ValueError("bad signature") from exc
    return json.loads(data)
