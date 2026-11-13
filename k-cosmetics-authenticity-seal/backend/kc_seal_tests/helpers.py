import dataclasses
import hashlib
import secrets
from pathlib import Path
from typing import Any

from kc_seal.config import Settings

# Random per test run; nothing secret is stored in the repository.
ADMIN_TOKEN = secrets.token_urlsafe(24)
PROXY_SECRET = secrets.token_hex(16)


def make_settings(tmp_path: Path, **overrides: Any) -> Settings:
    base = Settings(
        data_dir=tmp_path,
        signing_key_path=tmp_path / "keys" / "signing_key.pem",
        key_id="kc-seal-test-key",
        admin_token_sha256=hashlib.sha256(ADMIN_TOKEN.encode()).hexdigest(),
        official_origin="http://testserver",
        allowed_origins=("http://testserver",),
        app_proxy_secret=PROXY_SECRET,
        demo_mode=True,
        dev_generate_key=True,
        rate_limit_per_minute=600,
        rate_limit_burst=600,
    )
    return dataclasses.replace(base, **overrides)


def nonce() -> str:
    return secrets.token_urlsafe(18)
