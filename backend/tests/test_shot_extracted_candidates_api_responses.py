"""shot extracted candidates 接口响应壳测试。"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi.testclient import TestClient

from app.api.v1.routes.studio import shots as route
from app.dependencies import get_db
from app.main import app
from app.models.studio import ShotCandidateStatus, ShotCandidateType, ShotStatus


class _FakeDB:
    pass


def _override_db(db: _FakeDB):
    async def _get_db() -> AsyncGenerator[_FakeDB, None]:
        yield db

    return _get_db


def test_get_shot_extracted_candidates_returns_success_envelope(client: TestClient, monkeypatch) -> None:
    db = _FakeDB()

    class _Candidate:
        id = 1
        shot_id = "shot-1"
        candidate_type = ShotCandidateType.character
        candidate_name = "仙女A"
        candidate_status = ShotCandidateStatus.pending
        linked_entity_id = None
        source = "extraction"
        payload = {}
        confirmed_at = None
        created_at = "2026-01-01T00:00:00Z"
        updated_at = "2026-01-01T00:00:00Z"

    async def _fake_list(*_args, **_kwargs):
        return [_Candidate()]

    monkeypatch.setattr(route, "list_shot_extracted_candidates", _fake_list)
    app.dependency_overrides[get_db] = _override_db(db)
    try:
        response = client.get("/api/v1/studio/shots/shot-1/extracted-candidates")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["message"] == "success"
    assert body["data"][0]["candidate_name"] == "仙女A"
    assert body["data"][0]["candidate_status"] == "pending"


def test_update_shot_skip_extraction_returns_success_envelope(client: TestClient, monkeypatch) -> None:
    db = _FakeDB()

    class _Shot:
        id = "shot-1"
        chapter_id = "chapter-1"
        index = 1
        title = "镜头一"
        thumbnail = ""
        status = ShotStatus.ready
        skip_extraction = True
        script_excerpt = "摘录"
        generated_video_file_id = None

    async def _fake_set_skip(*_args, **_kwargs):
        return _Shot()

    monkeypatch.setattr(route, "set_skip_extraction", _fake_set_skip)
    app.dependency_overrides[get_db] = _override_db(db)
    try:
        response = client.patch(
            "/api/v1/studio/shots/shot-1/skip-extraction",
            json={"skip": True},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["data"]["skip_extraction"] is True
    assert body["data"]["status"] == "ready"


def test_link_extracted_candidate_returns_success_envelope(client: TestClient, monkeypatch) -> None:
    db = _FakeDB()

    class _Candidate:
        id = 2
        shot_id = "shot-1"
        candidate_type = ShotCandidateType.scene
        candidate_name = "河边"
        candidate_status = ShotCandidateStatus.linked
        linked_entity_id = "scene-1"
        source = "extraction"
        payload = {}
        confirmed_at = None
        created_at = "2026-01-01T00:00:00Z"
        updated_at = "2026-01-01T00:00:00Z"

    async def _fake_link(*_args, **_kwargs):
        return _Candidate()

    monkeypatch.setattr(route, "link_shot_extracted_candidate", _fake_link)
    app.dependency_overrides[get_db] = _override_db(db)
    try:
        response = client.patch(
            "/api/v1/studio/shots/extracted-candidates/2/link",
            json={"linked_entity_id": "scene-1"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["data"]["candidate_status"] == "linked"
    assert body["data"]["linked_entity_id"] == "scene-1"


def test_ignore_extracted_candidate_returns_success_envelope(client: TestClient, monkeypatch) -> None:
    db = _FakeDB()

    class _Candidate:
        id = 3
        shot_id = "shot-1"
        candidate_type = ShotCandidateType.prop
        candidate_name = "银斧头"
        candidate_status = ShotCandidateStatus.ignored
        linked_entity_id = None
        source = "extraction"
        payload = {}
        confirmed_at = None
        created_at = "2026-01-01T00:00:00Z"
        updated_at = "2026-01-01T00:00:00Z"

    async def _fake_ignore(*_args, **_kwargs):
        return _Candidate()

    monkeypatch.setattr(route, "ignore_shot_extracted_candidate", _fake_ignore)
    app.dependency_overrides[get_db] = _override_db(db)
    try:
        response = client.patch("/api/v1/studio/shots/extracted-candidates/3/ignore")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["data"]["candidate_status"] == "ignored"
