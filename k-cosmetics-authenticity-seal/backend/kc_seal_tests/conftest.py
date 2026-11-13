from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from kc_seal.api import create_app
from kc_seal.config import Settings
from kc_seal.seed import seed

from kc_seal_tests.helpers import ADMIN_TOKEN, make_settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return make_settings(tmp_path)


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    app = create_app(settings)
    seed(app.state.store, app.state.audit)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def admin() -> dict[str, str]:
    return {"Authorization": f"Bearer {ADMIN_TOKEN}"}
