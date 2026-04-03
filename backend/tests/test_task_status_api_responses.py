"""film/task_status 接口响应壳测试。"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.api.v1.routes.film import task_status as task_status_route
from app.core.task_manager.types import TaskStatus
from app.dependencies import get_db
from app.main import app
from app.models.task import GenerationDeliveryMode, GenerationTask, GenerationTaskStatus
from app.models.task_links import GenerationTaskLink, GenerationTaskLinkStatus


class _FakeResult:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def scalars(self):
        return self

    def first(self):
        return self._rows[0] if self._rows else None


class _FakeTaskDB:
    def __init__(self) -> None:
        self.tasks: dict[str, GenerationTask] = {}
        self.links: dict[int, GenerationTaskLink] = {}
        self._link_id = 1

    async def get(self, model: type, entity_id):
        if model is GenerationTask:
            return self.tasks.get(entity_id)
        if model is GenerationTaskLink:
            return self.links.get(entity_id)
        return None

    async def execute(self, *_args, **_kwargs):
        rows = list(self.links.values())
        return _FakeResult(rows)

    def add(self, obj: object) -> None:
        if isinstance(obj, GenerationTaskLink):
            if getattr(obj, "id", None) is None:
                obj.id = self._link_id
                self._link_id += 1
            self.links[obj.id] = obj

    async def flush(self) -> None:
        return None

    async def refresh(self, obj: object) -> None:
        now = datetime.now(UTC)
        if getattr(obj, "created_at", None) is None:
            obj.created_at = now
        obj.updated_at = now

    async def delete(self, obj: object) -> None:
        if isinstance(obj, GenerationTaskLink):
            self.links.pop(obj.id, None)


def _override_db(db: _FakeTaskDB):
    async def _get_db() -> AsyncGenerator[_FakeTaskDB, None]:
        yield db

    return _get_db


def test_get_task_status_not_found_returns_api_response(client: TestClient, monkeypatch) -> None:
    class _FakeStore:
        def __init__(self, _db) -> None:
            pass

        async def get_status_view(self, _task_id: str):
            return None

    monkeypatch.setattr(task_status_route, "SqlAlchemyTaskStore", _FakeStore)
    db = _FakeTaskDB()
    app.dependency_overrides[get_db] = _override_db(db)
    try:
        response = client.get("/api/v1/film/tasks/task-missing/status")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {"code": 404, "message": "Task not found", "data": None}


def test_get_task_result_not_found_returns_api_response(client: TestClient) -> None:
    db = _FakeTaskDB()
    app.dependency_overrides[get_db] = _override_db(db)
    try:
        response = client.get("/api/v1/film/tasks/task-missing/result")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {"code": 404, "message": "Task not found", "data": None}


def test_create_task_link_returns_created_envelope(client: TestClient) -> None:
    db = _FakeTaskDB()
    app.dependency_overrides[get_db] = _override_db(db)
    try:
        response = client.post(
            "/api/v1/film/task-links",
            json={
                "task_id": "task-1",
                "resource_type": "image",
                "relation_type": "prop",
                "relation_entity_id": "prop-1",
                "file_id": None,
                "status": "todo",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    body = response.json()
    assert body["code"] == 201
    assert body["message"] == "success"
    assert body["data"]["id"] == 1
    assert body["data"]["task_id"] == "task-1"


def test_get_task_link_not_found_returns_api_response(client: TestClient) -> None:
    db = _FakeTaskDB()
    app.dependency_overrides[get_db] = _override_db(db)
    try:
        response = client.get("/api/v1/film/task-links/999")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {"code": 404, "message": "Task link not found", "data": None}


def test_delete_task_link_returns_empty_envelope(client: TestClient) -> None:
    db = _FakeTaskDB()
    link = GenerationTaskLink(
        task_id="task-1",
        resource_type="image",
        relation_type="prop",
        relation_entity_id="prop-1",
        file_id=None,
        status=GenerationTaskLinkStatus.todo,
    )
    link.id = 1
    link.created_at = datetime.now(UTC)
    link.updated_at = link.created_at
    db.links[link.id] = link

    app.dependency_overrides[get_db] = _override_db(db)
    try:
        response = client.delete("/api/v1/film/task-links/1")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"code": 200, "message": "success", "data": None}
    assert 1 not in db.links


def test_get_task_result_returns_success_envelope(client: TestClient) -> None:
    db = _FakeTaskDB()
    task = GenerationTask(
        id="task-1",
        mode=GenerationDeliveryMode.async_polling,
        status=GenerationTaskStatus.succeeded,
        progress=100,
        payload={},
        result={"url": "https://example.com/video.mp4"},
        error="",
    )
    task.created_at = datetime.now(UTC)
    task.updated_at = task.created_at
    db.tasks[task.id] = task

    app.dependency_overrides[get_db] = _override_db(db)
    try:
        response = client.get("/api/v1/film/tasks/task-1/result")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["message"] == "success"
    assert body["data"]["task_id"] == "task-1"
    assert body["data"]["status"] == TaskStatus.succeeded.value
