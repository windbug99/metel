from scripts.backfill_oauth_granted_scopes import _needs_backfill, _normalize_scopes


def test_normalize_scopes_handles_list_and_string():
    assert _normalize_scopes(["read", " write ", "", None]) == ["read", "write"]
    assert _normalize_scopes("read write") == ["read", "write"]
    assert _normalize_scopes(None) == []


def test_needs_backfill_only_for_supported_provider_without_scopes():
    assert _needs_backfill("google", []) is True
    assert _needs_backfill("linear", None) is True
    assert _needs_backfill("notion", "insert_content") is False
    assert _needs_backfill("spotify", []) is False
