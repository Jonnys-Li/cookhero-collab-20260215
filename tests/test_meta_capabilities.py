def test_meta_capabilities_contains_community_ai_modes(run):
    from app.api.v1.endpoints import meta

    payload = run(meta.get_capabilities())
    assert isinstance(payload, dict)

    modes = payload.get("community_ai_modes")
    assert isinstance(modes, list)
    assert "polish" in modes
    assert "card" in modes
