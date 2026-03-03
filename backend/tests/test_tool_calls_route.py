import asyncio
from types import SimpleNamespace

from fastapi import HTTPException
from starlette.requests import Request

from app.routes.tool_calls import (
    list_tool_calls,
    tool_calls_connectors,
    tool_calls_failure_breakdown,
    tool_calls_overview,
    tool_calls_trends,
)


def _request() -> Request:
    scope = {"type": "http", "method": "GET", "path": "/api/tool-calls", "headers": []}
    return Request(scope)


def test_list_tool_calls_applies_filters(monkeypatch):
    class _Query:
        def __init__(self, client, table_name: str):
            self.client = client
            self.table_name = table_name
            self.selected = ""
            self.ops: list[tuple[str, str, object]] = []

        def select(self, fields: str, **_kwargs):
            self.selected = fields
            return self

        def eq(self, field: str, value):
            self.ops.append(("eq", field, value))
            return self

        def gte(self, field: str, value):
            self.ops.append(("gte", field, value))
            return self

        def lte(self, field: str, value):
            self.ops.append(("lte", field, value))
            return self

        def order(self, field: str, **_kwargs):
            self.ops.append(("order", field, None))
            return self

        def limit(self, value: int):
            self.ops.append(("limit", "limit", value))
            return self

        def execute(self):
            self.client.query_logs.append((self.table_name, self.selected, list(self.ops)))
            if self.table_name == "tool_calls" and self.selected.startswith("id,api_key_id"):
                return SimpleNamespace(
                    data=[
                        {
                            "id": 10,
                            "api_key_id": 1,
                            "tool_name": "linear_list_issues",
                            "status": "success",
                            "error_code": None,
                            "latency_ms": 120,
                            "created_at": "2026-03-02T00:00:00+00:00",
                        }
                    ]
                )
            if self.table_name == "tool_calls" and self.selected == "status,error_code":
                return SimpleNamespace(
                    data=[
                        {"status": "success", "error_code": None},
                        {"status": "fail", "error_code": "policy_blocked"},
                        {"status": "fail", "error_code": "upstream_temporary_failure"},
                    ]
                )
            if self.table_name == "api_keys":
                return SimpleNamespace(data=[{"id": 1, "name": "prod", "key_prefix": "metel_prod"}])
            return SimpleNamespace(data=[])

    class _Client:
        def __init__(self):
            self.query_logs: list[tuple[str, str, list[tuple[str, str, object]]]] = []

        def table(self, name: str):
            return _Query(self, name)

    client = _Client()

    async def _fake_user(_request: Request) -> str:
        return "user-1"

    monkeypatch.setattr("app.routes.tool_calls.get_authenticated_user_id", _fake_user)
    monkeypatch.setattr("app.routes.tool_calls.create_client", lambda *_args, **_kwargs: client)
    monkeypatch.setattr(
        "app.routes.tool_calls.get_settings",
        lambda: SimpleNamespace(supabase_url="https://example.supabase.co", supabase_service_role_key="service-role-key"),
    )

    out = asyncio.run(
        list_tool_calls(
            _request(),
            limit=20,
            status="success",
            tool_name="linear_list_issues",
            api_key_id=1,
            from_="2026-03-01T00:00:00Z",
            to="2026-03-03T00:00:00Z",
        )
    )

    assert out["count"] == 1
    assert out["items"][0]["tool_name"] == "linear_list_issues"
    assert out["summary"]["calls_24h"] == 3
    assert out["summary"]["success_24h"] == 1
    assert out["summary"]["fail_24h"] == 2
    assert out["summary"]["fail_rate_24h"] == 0.6667
    assert out["summary"]["blocked_rate_24h"] == 0.3333
    assert out["summary"]["retryable_fail_rate_24h"] == 0.3333
    assert out["summary"]["policy_blocked_24h"] == 1
    assert out["summary"]["upstream_temporary_24h"] == 1
    assert out["summary"]["access_denied_24h"] == 0
    assert out["summary"]["high_risk_allowed_24h"] == 0
    assert out["summary"]["policy_override_usage_24h"] == 0.0
    assert out["summary"]["top_failure_codes"][0]["error_code"] in {"policy_blocked", "upstream_temporary_failure"}

    tool_calls_queries = [item for item in client.query_logs if item[0] == "tool_calls"]
    assert len(tool_calls_queries) >= 2
    flattened = [op for _, _, ops in tool_calls_queries for op in ops]
    assert ("eq", "status", "success") in flattened
    assert ("eq", "tool_name", "linear_list_issues") in flattened
    assert ("eq", "api_key_id", 1) in flattened
    assert any(op[0] == "gte" and op[1] == "created_at" for op in flattened)
    assert any(op[0] == "lte" and op[1] == "created_at" for op in flattened)


def test_list_tool_calls_invalid_datetime_raises(monkeypatch):
    async def _fake_user(_request: Request) -> str:
        return "user-1"

    monkeypatch.setattr("app.routes.tool_calls.get_authenticated_user_id", _fake_user)
    monkeypatch.setattr(
        "app.routes.tool_calls.get_settings",
        lambda: SimpleNamespace(supabase_url="https://example.supabase.co", supabase_service_role_key="service-role-key"),
    )
    monkeypatch.setattr("app.routes.tool_calls.create_client", lambda *_args, **_kwargs: SimpleNamespace(table=lambda _name: None))

    try:
        asyncio.run(
            list_tool_calls(
                _request(),
                limit=20,
                status="all",
                tool_name="",
                api_key_id=None,
                from_="not-a-date",
                to="",
            )
        )
    except HTTPException as exc:
        assert exc.status_code == 400
        assert exc.detail == "invalid_datetime:from"
    else:
        assert False, "expected HTTPException"


def test_tool_calls_overview_and_breakdown(monkeypatch):
    class _Query:
        def __init__(self, client, table_name: str):
            self.client = client
            self.table_name = table_name
            self.selected = ""
            self.ops: list[tuple[str, str, object]] = []

        def select(self, fields: str, **_kwargs):
            self.selected = fields
            return self

        def eq(self, field: str, value):
            self.ops.append(("eq", field, value))
            return self

        def gte(self, field: str, value):
            self.ops.append(("gte", field, value))
            return self

        def lte(self, field: str, value):
            self.ops.append(("lte", field, value))
            return self

        def execute(self):
            if self.table_name == "tool_calls":
                if any(op[0] == "lte" for op in self.ops):
                    return SimpleNamespace(
                        data=[
                            {
                                "id": 11,
                                "api_key_id": 1,
                                "tool_name": "notion_search",
                                "status": "success",
                                "error_code": None,
                                "latency_ms": 50,
                                "created_at": "2026-03-01T00:00:00+00:00",
                            }
                        ]
                    )
                return SimpleNamespace(
                    data=[
                        {
                            "id": 1,
                            "api_key_id": 1,
                            "tool_name": "notion_search",
                            "status": "success",
                            "error_code": None,
                            "latency_ms": 80,
                            "created_at": "2026-03-02T00:00:00+00:00",
                        },
                        {
                            "id": 2,
                            "api_key_id": 1,
                            "tool_name": "linear_list_issues",
                            "status": "fail",
                            "error_code": "policy_blocked",
                            "latency_ms": 100,
                            "created_at": "2026-03-02T00:01:00+00:00",
                        },
                        {
                            "id": 3,
                            "api_key_id": 2,
                            "tool_name": "linear_get_viewer",
                            "status": "fail",
                            "error_code": "upstream_temporary_failure",
                            "latency_ms": 120,
                            "created_at": "2026-03-02T00:02:00+00:00",
                        },
                    ]
                )
            if self.table_name == "api_keys":
                return SimpleNamespace(data=[{"id": 1, "name": "prod", "key_prefix": "metel_prod"}])
            return SimpleNamespace(data=[])

    class _Client:
        def table(self, name: str):
            return _Query(self, name)

    async def _fake_user(_request: Request) -> str:
        return "user-1"

    monkeypatch.setattr("app.routes.tool_calls.get_authenticated_user_id", _fake_user)
    monkeypatch.setattr("app.routes.tool_calls.create_client", lambda *_args, **_kwargs: _Client())
    monkeypatch.setattr(
        "app.routes.tool_calls.get_settings",
        lambda: SimpleNamespace(supabase_url="https://example.supabase.co", supabase_service_role_key="service-role-key"),
    )

    overview = asyncio.run(tool_calls_overview(_request(), hours=24))
    assert overview["kpis"]["total_calls"] == 3
    assert overview["kpis"]["p95_latency_ms"] == 120
    assert overview["top"]["called_tools"][0]["count"] >= 1

    trends = asyncio.run(tool_calls_trends(_request(), days=7, bucket="day"))
    assert len(trends["items"]) >= 1

    breakdown = asyncio.run(tool_calls_failure_breakdown(_request(), days=7))
    assert breakdown["total_failures"] == 2
    assert any(item["category"] == "policy_blocked" for item in breakdown["categories"])

    connectors = asyncio.run(tool_calls_connectors(_request(), days=7))
    assert any(item["connector"] == "linear" for item in connectors["items"])
