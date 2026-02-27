from agent.runtime_catalog import get_catalog, get_or_create_catalog_id, invalidate_catalog


def test_get_or_create_catalog_id_reuses_same_payload():
    payload = {"connected_services": ["notion"], "enabled_api_ids": ["notion_search"]}
    catalog_id_1, created_1 = get_or_create_catalog_id(user_id="u1", catalog_payload=payload, ttl_sec=600)
    catalog_id_2, created_2 = get_or_create_catalog_id(user_id="u1", catalog_payload=payload, ttl_sec=600)

    assert created_1 is True
    assert created_2 is False
    assert catalog_id_1 == catalog_id_2
    assert isinstance(get_catalog(catalog_id_1), dict)


def test_invalidate_catalog_removes_entries_for_user():
    payload = {"connected_services": ["linear"], "enabled_api_ids": ["linear_search_issues"]}
    catalog_id, _ = get_or_create_catalog_id(user_id="u_invalidate", catalog_payload=payload, ttl_sec=600)
    assert get_catalog(catalog_id) is not None

    removed = invalidate_catalog("u_invalidate", reason="scope_changed")
    assert removed >= 1
    assert get_catalog(catalog_id) is None
