"""LLM 接口响应壳测试：聚焦 Provider CRUD。"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.dependencies import get_db
from app.main import app
from app.models.llm import Provider, ProviderStatus


class _FakeLlmDB:
    """最小 DB 替身：仅覆盖 Provider 路由测试所需行为。"""

    def __init__(self) -> None:
        self.providers: dict[str, Provider] = {}

    async def get(self, model: type, entity_id: str) -> Provider | None:  # noqa: ANN401
        if model is not Provider:
            return None
        return self.providers.get(entity_id)

    def add(self, obj: Provider) -> None:
        self.providers[obj.id] = obj

    async def flush(self) -> None:
        return None

    async def refresh(self, obj: Provider) -> None:
        now = datetime.now(UTC)
        if getattr(obj, "created_at", None) is None:
            obj.created_at = now
        obj.updated_at = now

    async def delete(self, obj: Provider) -> None:
        self.providers.pop(obj.id, None)


def _seed_provider(db: _FakeLlmDB, provider_id: str = "p-1") -> Provider:
    now = datetime.now(UTC)
    obj = Provider(
        id=provider_id,
        name="OpenAI",
        base_url="https://api.openai.com/v1",
        api_key="secret",
        api_secret="",
        description="说明",
        status=ProviderStatus.testing,
        created_by="tester",
    )
    obj.created_at = now
    obj.updated_at = now
    db.providers[obj.id] = obj
    return obj


def _override_db(db: _FakeLlmDB):
    async def _get_db() -> AsyncGenerator[_FakeLlmDB, None]:
        yield db

    return _get_db


def test_create_provider_returns_created_envelope(client: TestClient) -> None:
    db = _FakeLlmDB()
    app.dependency_overrides[get_db] = _override_db(db)
    try:
        response = client.post(
            "/api/v1/llm/providers",
            json={
                "id": "p-create",
                "name": "OpenAI",
                "base_url": "https://api.openai.com/v1",
                "api_key": "secret",
                "api_secret": "",
                "description": "说明",
                "status": "testing",
                "created_by": "tester",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    body = response.json()
    assert body["code"] == 201
    assert body["message"] == "success"
    assert body["data"]["id"] == "p-create"
    assert body["data"]["name"] == "OpenAI"
    assert body["data"]["base_url"] == "https://api.openai.com/v1"
    assert "api_key" not in body["data"]


def test_get_provider_not_found_returns_api_response(client: TestClient) -> None:
    db = _FakeLlmDB()
    app.dependency_overrides[get_db] = _override_db(db)
    try:
        response = client.get("/api/v1/llm/providers/missing")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {"code": 404, "message": "Provider not found", "data": None}


def test_delete_provider_returns_empty_envelope(client: TestClient) -> None:
    db = _FakeLlmDB()
    _seed_provider(db, "p-delete")
    app.dependency_overrides[get_db] = _override_db(db)
    try:
        response = client.delete("/api/v1/llm/providers/p-delete")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"code": 200, "message": "success", "data": None}
    assert "p-delete" not in db.providers


def test_create_provider_validation_error_returns_api_response(client: TestClient) -> None:
    db = _FakeLlmDB()
    app.dependency_overrides[get_db] = _override_db(db)
    try:
        response = client.post(
            "/api/v1/llm/providers",
            json={
                "id": "p-invalid",
                "name": "OpenAI",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == 422
    assert body["data"] is None
    assert "base_url" in body["message"]
