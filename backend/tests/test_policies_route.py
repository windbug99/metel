import asyncio
from types import SimpleNamespace

from starlette.requests import Request

from app.routes.policies import SimulatePolicyRequest, simulate_policy


def _request() -> Request:
    scope = {"type": "http", "method": "POST", "path": "/api/policies/simulate", "headers": []}
    return Request(scope)


def test_simulate_policy_blocks_by_deny_tools(monkeypatch):
    class _Query:
        def select(self, *_args, **_kwargs):
            return self

        def eq(self, *_args, **_kwargs):
            return self

        def limit(self, *_args, **_kwargs):
            return self

        def execute(self):
            return SimpleNamespace(
                data=[
                    {
                        "id": 1,
                        "name": "prod",
                        "key_prefix": "metel_prod",
                        "is_active": True,
                        "allowed_tools": None,
                        "policy_json": {"deny_tools": ["linear_list_issues"]},
                    }
                ]
            )

    class _Client:
        def table(self, _name: str):
            return _Query()

    async def _fake_user(_request: Request) -> str:
        return "user-1"

    monkeypatch.setattr("app.routes.policies.get_authenticated_user_id", _fake_user)
    monkeypatch.setattr("app.routes.policies.create_client", lambda *_args, **_kwargs: _Client())
    monkeypatch.setattr(
        "app.routes.policies.get_settings",
        lambda: SimpleNamespace(supabase_url="x", supabase_service_role_key="y"),
    )
    monkeypatch.setattr(
        "app.routes.policies.load_registry",
        lambda: SimpleNamespace(get_tool=lambda _name: SimpleNamespace(service="linear")),
    )

    out = asyncio.run(
        simulate_policy(
            _request(),
            SimulatePolicyRequest(api_key_id=1, tool_name="linear_list_issues", arguments={}),
        )
    )
    assert out["decision"] == "blocked"
    assert any(item["code"] == "access_denied" for item in out["reasons"])


def test_simulate_policy_allows_safe_request(monkeypatch):
    class _Query:
        def select(self, *_args, **_kwargs):
            return self

        def eq(self, *_args, **_kwargs):
            return self

        def limit(self, *_args, **_kwargs):
            return self

        def execute(self):
            return SimpleNamespace(data=[])

    class _Client:
        def table(self, _name: str):
            return _Query()

    async def _fake_user(_request: Request) -> str:
        return "user-1"

    monkeypatch.setattr("app.routes.policies.get_authenticated_user_id", _fake_user)
    monkeypatch.setattr("app.routes.policies.create_client", lambda *_args, **_kwargs: _Client())
    monkeypatch.setattr(
        "app.routes.policies.get_settings",
        lambda: SimpleNamespace(supabase_url="x", supabase_service_role_key="y"),
    )
    monkeypatch.setattr(
        "app.routes.policies.load_registry",
        lambda: SimpleNamespace(get_tool=lambda _name: SimpleNamespace(service="notion")),
    )

    out = asyncio.run(
        simulate_policy(
            _request(),
            SimulatePolicyRequest(api_key_id=None, tool_name="notion_search", arguments={"query": "hello"}),
        )
    )
    assert out["decision"] == "allowed"
