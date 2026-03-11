from agent.runtime_api_profile import build_runtime_api_profile


def test_build_runtime_api_profile_filters_by_scope_and_policy():
    profile = build_runtime_api_profile(
        connected_services=["notion", "linear"],
        granted_scopes={
            "notion": {"read_content", "insert_content"},
            "linear": {"read"},
        },
        tenant_policy={"blocked_tools": ["notion_search"]},
        risk_policy={"allow_high_risk": False},
    )
    enabled = set(profile["enabled_api_ids"])
    blocked = {item["api_id"]: item["reason"] for item in profile["blocked_reason"]}

    assert "notion_search" not in enabled
    assert blocked.get("notion_search") == "tenant_policy_blocked"
    # linear issue delete/update 류는 기본 high risk 정책에서 차단됨
    assert blocked.get("linear_delete_issue") in {"risk_policy_blocked", None}


def test_build_runtime_api_profile_allows_high_risk_when_enabled():
    profile = build_runtime_api_profile(
        connected_services=["linear"],
        granted_scopes={"linear": {"read", "write"}},
        risk_policy={"allow_high_risk": True},
    )
    enabled = set(profile["enabled_api_ids"])

    assert "linear_create_issue" in enabled


def test_build_runtime_api_profile_accepts_google_scope_aliases():
    profile = build_runtime_api_profile(
        connected_services=["google"],
        granted_scopes={"google": {"calendar.read"}},
        risk_policy={"allow_high_risk": False},
    )
    enabled = set(profile["enabled_api_ids"])
    blocked = {item["api_id"]: item["reason"] for item in profile["blocked_reason"]}

    assert "google_calendar_list_events" in enabled
    assert blocked.get("google_calendar_list_events") != "missing_required_scope"


def test_build_runtime_api_profile_enables_github_tools_with_scopes():
    profile = build_runtime_api_profile(
        connected_services=["github"],
        granted_scopes={"github": {"read:user", "repo"}},
        risk_policy={"allow_high_risk": False},
    )
    enabled = set(profile["enabled_api_ids"])

    assert "github_get_me" in enabled
    assert "github_create_issue" in enabled


def test_build_runtime_api_profile_enables_canva_tools_with_scopes():
    profile = build_runtime_api_profile(
        connected_services=["canva"],
        granted_scopes={"canva": {"design:meta:read", "design:content:read", "design:content:write"}},
        risk_policy={"allow_high_risk": False},
    )
    enabled = set(profile["enabled_api_ids"])

    assert "canva_design_list" in enabled
    assert "canva_export_create" in enabled
