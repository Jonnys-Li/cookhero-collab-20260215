from __future__ import annotations

import asyncio
import importlib
from types import SimpleNamespace

import pytest


class FakeDoc:
    def __init__(self, *, doc_id: str, dish_name: str, category: str, difficulty: str, content: str):
        self.id = doc_id
        self.dish_name = dish_name
        self.category = category
        self.difficulty = difficulty
        self.content = content

    def to_dict(self):
        return {
            "id": self.id,
            "dish_name": self.dish_name,
            "category": self.category,
            "difficulty": self.difficulty,
            "content": self.content,
        }


def test_personal_document_service_crud_calls_repo_and_rag(monkeypatch):
    svc_mod = importlib.import_module("app.services.personal_document_service")
    service = svc_mod.PersonalDocumentService()

    calls = {"create": [], "delete": [], "list": [], "add": [], "update": [], "del_vs": []}

    async def fake_create(**kwargs):
        calls["create"].append(kwargs)
        doc_id = kwargs.get("doc_id") or "d1"
        return FakeDoc(
            doc_id=str(doc_id),
            dish_name=kwargs["dish_name"],
            category=kwargs["category"],
            difficulty=kwargs["difficulty"],
            content=kwargs["content"],
        )

    async def fake_get_by_id_for_user(document_id: str, user_id: str):
        if document_id == "missing":
            return None
        return FakeDoc(doc_id=document_id, dish_name="x", category="c", difficulty="d", content="ct")

    async def fake_delete(document_id: str, user_id: str):
        calls["delete"].append((document_id, user_id))
        return document_id != "missing"

    async def fake_list_by_user(user_id: str, limit: int, offset: int):
        calls["list"].append((user_id, limit, offset))
        return [
            FakeDoc(doc_id="d1", dish_name="a", category="c", difficulty="d", content="ct"),
        ]

    monkeypatch.setattr(svc_mod.document_repository, "create", fake_create)
    monkeypatch.setattr(svc_mod.document_repository, "get_by_id_for_user", fake_get_by_id_for_user)
    monkeypatch.setattr(svc_mod.document_repository, "delete", fake_delete)
    monkeypatch.setattr(svc_mod.document_repository, "list_by_user", fake_list_by_user)
    monkeypatch.setattr(svc_mod.document_repository, "get_metadata_options", lambda _u: {"dish_name": ["a"]})

    async def fake_add_personal_document(**kwargs):
        calls["add"].append(kwargs)

    async def fake_update_personal_document(**kwargs):
        calls["update"].append(kwargs)

    async def fake_delete_personal_document(**kwargs):
        calls["del_vs"].append(kwargs)

    monkeypatch.setattr(svc_mod.rag_service_instance, "add_personal_document", fake_add_personal_document)
    monkeypatch.setattr(svc_mod.rag_service_instance, "update_personal_document", fake_update_personal_document)
    monkeypatch.setattr(svc_mod.rag_service_instance, "delete_personal_document", fake_delete_personal_document)

    async def _run():
        doc = await service.create_document(
            user_id="u1",
            dish_name="dish",
            category="cat",
            difficulty="easy",
            data_source="recipes",
            content="c",
        )
        assert doc.dish_name == "dish"
        assert calls["add"] and calls["add"][0]["user_id"] == "u1"

        fetched = await service.get_document("u1", "d1")
        assert fetched and fetched["id"] == "d1"
        assert await service.get_document("u1", "missing") is None

        updated = await service.update_document(
            user_id="u1",
            document_id="d1",
            dish_name="dish2",
            category="cat",
            difficulty="easy",
            data_source="tips",
            content="c2",
        )
        assert updated is not None
        assert calls["update"]

        assert await service.delete_document("u1", "d1") is True
        assert calls["del_vs"]

        assert await service.delete_document("u1", "missing") is False

        docs = await service.list_documents("u1", limit=10, offset=0)
        assert docs and docs[0]["id"] == "d1"

        assert service.get_available_options("u1") == {"dish_name": ["a"]}

    asyncio.run(_run())


def test_personal_document_service_rejects_invalid_data_source():
    svc_mod = importlib.import_module("app.services.personal_document_service")
    service = svc_mod.PersonalDocumentService()

    async def _run():
        with pytest.raises(ValueError):
            await service.create_document(
                user_id="u1",
                dish_name="dish",
                category="cat",
                difficulty="easy",
                data_source="invalid",
                content="c",
            )

        with pytest.raises(ValueError):
            await service.update_document(
                user_id="u1",
                document_id="d1",
                dish_name="dish",
                category="cat",
                difficulty="easy",
                data_source="invalid",
                content="c",
            )

    asyncio.run(_run())

