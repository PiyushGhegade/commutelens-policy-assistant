from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.llm import FakeLLM
from app.main import create_app
from app.store import PolicyStore


@pytest.fixture
def settings(tmp_path):
    return Settings(_env_file=None, data_dir=tmp_path, llm_provider="fake", embedding_model="hash-test")


@pytest.fixture
def store(settings):
    s = PolicyStore(settings.data_dir, "hash-test")
    s.seed(Path(__file__).resolve().parents[1] / "policies")
    yield s
    s.close()


@pytest.fixture
def client(settings, store):
    with TestClient(create_app(settings, store=store, llm=FakeLLM())) as c:
        yield c


def auth(client, username="asha"):
    result = client.post("/auth/demo-token", json={"username": username, "password": "commute-demo"})
    assert result.status_code == 200
    return {"Authorization": f"Bearer {result.json()['access_token']}"}
