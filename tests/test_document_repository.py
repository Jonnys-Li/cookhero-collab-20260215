from __future__ import annotations

import asyncio
import importlib
import uuid


document_repo_mod = importlib.import_module("app.database.document_repository")
DocumentRepository = getattr(document_repo_mod, "DocumentRepository")


def test_document_repository_crud_and_metadata_cache(monkeypatch, sqlite_session_context):
    monkeypatch.setattr(document_repo_mod, "get_session_context", sqlite_session_context)

    # Reset class-level caches to keep the test deterministic.
    DocumentRepository._global_cache = {}
    DocumentRepository._user_cache = {}
    DocumentRepository._cache_initialized = False

    user_uuid = uuid.uuid4()
    other_uuid = uuid.uuid4()

    async def _run():
        # KnowledgeDocumentModel.user_id has an FK to users.id; seed users first.
        from app.database.models import UserModel

        async with sqlite_session_context() as session:
            session.add(
                UserModel(id=user_uuid, username="u-cache", password_hash="x")
            )
            session.add(
                UserModel(id=other_uuid, username="u-other", password_hash="x")
            )
            await session.flush()

        # Seed documents via batch API (does not update cache; cache is loaded from DB below).
        await DocumentRepository.create_batch(
            [
                {
                    "user_id": None,
                    "dish_name": "Mapo tofu",
                    "category": "川菜",
                    "difficulty": "easy",
                    "data_source": "recipes",
                    "source_type": "recipes",
                    "source": "s1",
                    "is_dish_index": False,
                    "content": "global content",
                },
                {
                    "user_id": str(user_uuid),
                    "dish_name": "My dish",
                    "category": "personal",
                    "difficulty": "easy",
                    "data_source": "personal",
                    "source_type": "personal",
                    "source": "u1",
                    "is_dish_index": False,
                    "content": "personal content",
                },
            ]
        )

        await DocumentRepository.init_all_metadata_cache()

        merged = DocumentRepository.get_metadata_options(user_id=str(user_uuid))
        assert "dish_name" in merged and "Mapo tofu" in merged["dish_name"]
        assert "My dish" in merged["dish_name"]

        catalog = DocumentRepository.get_metadata_for_filter(user_id=str(user_uuid))
        assert "Global Recipes" in catalog
        assert "Personal Documents" in catalog

        # Creating a personal doc should update the user cache incrementally.
        personal = await DocumentRepository.create(
            user_id=str(other_uuid),
            dish_name="Salad",
            category="health",
            difficulty="easy",
            data_source="personal",
            source_type="personal",
            source="s2",
            content="c1",
        )
        personal_id = str(personal.id)

        # Global create triggers a NotImplementedError cache path; keep that behavior explicit.
        try:
            await DocumentRepository.create(
                user_id=None,
                dish_name="Global",
                category="x",
                difficulty="easy",
                data_source="recipes",
                source_type="recipes",
                source="s3",
                content="c2",
            )
        except NotImplementedError:
            pass
        else:
            raise AssertionError("Expected NotImplementedError for global cache update path")

        fetched = await DocumentRepository.get_by_id(personal_id)
        assert fetched is not None and fetched.dish_name == "Salad"
        assert await DocumentRepository.get_by_id("bad") is None

        assert (
            await DocumentRepository.get_by_id_for_user(personal_id, str(other_uuid))
        ) is not None
        assert (
            await DocumentRepository.get_by_id_for_user(personal_id, str(user_uuid))
        ) is None

        docs = await DocumentRepository.get_by_ids([personal_id])
        assert personal_id in docs
        assert await DocumentRepository.get_by_ids(["bad"]) == {}

        parents = await DocumentRepository.get_parent_documents([personal_id])
        assert personal_id in parents
        assert parents[personal_id].page_content == "c1"

        updated = await DocumentRepository.update(
            personal_id,
            user_id=str(other_uuid),
            dish_name="Salad 2",
        )
        assert updated is not None and updated.dish_name == "Salad 2"
        assert await DocumentRepository.update("bad", dish_name="x") is None

        user_docs = await DocumentRepository.list_by_user(str(other_uuid), limit=10, offset=0)
        assert any(str(d.id) == personal_id for d in user_docs)

        assert await DocumentRepository.count_by_data_source("personal") >= 2

        deleted = await DocumentRepository.delete(personal_id, user_id=str(other_uuid))
        assert deleted is True
        assert await DocumentRepository.get_by_id(personal_id) is None

        # Delete by data_source should return an integer count.
        count = await DocumentRepository.delete_by_data_source("recipes")
        assert isinstance(count, int)

    asyncio.run(_run())
