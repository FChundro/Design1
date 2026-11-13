"""Runtime settings, read from environment variables only.

Secrets (signing key, admin token, Shopify app proxy secret, privacy salt) are
never committed. In production they come from a secret manager / KMS; see
docs/DEPLOYMENT.md.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path


def _bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _csv(name: str, default: str) -> tuple[str, ...]:
    raw = os.environ.get(name, default)
    return tuple(part.strip().rstrip("/") for part in raw.split(",") if part.strip())


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    signing_key_path: Path
    key_id: str
    admin_token_sha256: str
    official_origin: str
    allowed_origins: tuple[str, ...]
    app_proxy_secret: str | None = None
    require_app_proxy: bool = False
    heartbeat_interval_s: int = 60
    response_ttl_s: int = 120
    rate_limit_per_minute: int = 20
    rate_limit_burst: int = 10
    access_log_retention_days: int = 30
    environment: str = "prototype"
    demo_mode: bool = False
    dev_generate_key: bool = False
    extra: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> Settings:
        data_dir = Path(os.environ.get("KC_SEAL_DATA_DIR", "./var")).resolve()
        official = os.environ.get("KC_SEAL_OFFICIAL_ORIGIN", "http://127.0.0.1:8787")
        return cls(
            data_dir=data_dir,
            signing_key_path=Path(
                os.environ.get(
                    "KC_SEAL_SIGNING_KEY_PATH",
                    str(data_dir / "keys" / "signing_key.pem"),
                )
            ),
            key_id=os.environ.get("KC_SEAL_KEY_ID", "kc-seal-test-2026-11"),
            admin_token_sha256=os.environ.get("KC_SEAL_ADMIN_TOKEN_SHA256", ""),
            official_origin=official.rstrip("/"),
            allowed_origins=_csv("KC_SEAL_ALLOWED_ORIGINS", official),
            app_proxy_secret=os.environ.get("KC_SEAL_APP_PROXY_SECRET") or None,
            require_app_proxy=_bool("KC_SEAL_REQUIRE_APP_PROXY"),
            heartbeat_interval_s=int(
                os.environ.get("KC_SEAL_HEARTBEAT_INTERVAL_S", "60")
            ),
            rate_limit_per_minute=int(
                os.environ.get("KC_SEAL_RATE_LIMIT_PER_MINUTE", "20")
            ),
            environment=os.environ.get("KC_SEAL_ENVIRONMENT", "prototype"),
            demo_mode=_bool("KC_SEAL_DEMO_MODE"),
            dev_generate_key=_bool("KC_SEAL_DEV_GENERATE_KEY"),
        )
