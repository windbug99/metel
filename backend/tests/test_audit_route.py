import asyncio
from types import SimpleNamespace

from fastapi import HTTPException
from starlette.requests import Request

from app.routes.audit import export_audit_events, get_audit_event_detail, list_audit_events


def _request() -> Request:
    scope = {"type": "http", "method": "GET", "path": "/api/audit/events", "headers": []}
    return Request(scope)


def test_list_audit_events_filters_and_maps_decisions(monkeypatch):
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
            if self.table_name == "tool_calls":
                return SimpleNamespace(
                    data=[
                        {
                            "id": 1,
                            "request_id": "r1",
                            "api_key_id": 10,
                            "tool_name": "notion_search",
                            "status": "success",
                            "error_code": None,
                            "latency_ms": 100,
                            "created_at": "2026-03-03T00:00:00+00:00",
                        },
                        {
                            "id": 2,
                            "request_id": "r2",
                            "api_key_id": 10,
                            "tool_name": "notion_delete_block",
                            "status": "fail",
                            "error_code": "policy_blocked",
                            "latency_ms": 50,
                            "created_at": "2026-03-03T00:01:00+00:00",
                        },
                    ]
                )
            if self.table_name == "api_keys":
                return SimpleNamespace(data=[{"id": 10, "name": "prod", "key_prefix": "metel_prod"}])
            return SimpleNamespace(data=[])

    class _Client:
        def __init__(self):
            self.query_logs: list[tuple[str, str, list[tuple[str, str, object]]]] = []

        def table(self, name: str):
            return _Query(self, name)

    client = _Client()

    async def _fake_user(_request: Request) -> str:
        return "user-1"

    monkeypatch.setattr("app.routes.audit.get_authenticated_user_id", _fake_user)
    monkeypatch.setattr("app.routes.audit.create_client", lambda *_args, **_kwargs: client)
    monkeypatch.setattr(
        "app.routes.audit.get_settings",
        lambda: SimpleNamespace(supabase_url="https://example.supabase.co", supabase_service_role_key="service-role-key"),
    )

    out = asyncio.run(
        list_audit_events(
            _request(),
            limit=50,
            status="all",
            tool_name="",
            api_key_id=10,
            error_code="",
            from_="2026-03-01T00:00:00Z",
            to="2026-03-04T00:00:00Z",
        )
    )

    assert out["count"] == 2
    assert out["summary"]["allowed_count"] == 1
    assert out["summary"]["high_risk_allowed_count"] == 0
    assert out["summary"]["policy_override_usage"] == 0.0
    assert out["summary"]["policy_blocked_count"] == 1
    assert out["items"][0]["actor"]["api_key"]["name"] == "prod"
    assert out["items"][0]["outcome"]["decision"] == "allowed"
    assert out["items"][1]["outcome"]["decision"] == "policy_blocked"

    tool_calls_queries = [item for item in client.query_logs if item[0] == "tool_calls"]
    assert len(tool_calls_queries) >= 1
    flattened = [op for _, _, ops in tool_calls_queries for op in ops]
    assert ("eq", "api_key_id", 10) in flattened
    assert any(op[0] == "gte" and op[1] == "created_at" for op in flattened)
    assert any(op[0] == "lte" and op[1] == "created_at" for op in flattened)


def test_list_audit_events_invalid_datetime_raises(monkeypatch):
    async def _fake_user(_request: Request) -> str:
        return "user-1"

    monkeypatch.setattr("app.routes.audit.get_authenticated_user_id", _fake_user)
    monkeypatch.setattr(
        "app.routes.audit.get_settings",
        lambda: SimpleNamespace(supabase_url="https://example.supabase.co", supabase_service_role_key="service-role-key"),
    )
    monkeypatch.setattr("app.routes.audit.create_client", lambda *_args, **_kwargs: SimpleNamespace(table=lambda _name: None))

    try:
        asyncio.run(
            list_audit_events(
                _request(),
                limit=50,
                status="all",
                tool_name="",
                api_key_id=None,
                error_code="",
                from_="not-a-date",
                to="",
            )
        )
    except HTTPException as exc:
        assert exc.status_code == 400
        assert exc.detail == "invalid_datetime:from"
    else:
        assert False, "expected HTTPException"


def test_export_audit_events_jsonl(monkeypatch):
    class _Query:
        def __init__(self, table_name: str):
            self.table_name = table_name

        def select(self, *_args, **_kwargs):
            return self

        def eq(self, *_args, **_kwargs):
            return self

        def gte(self, *_args, **_kwargs):
            return self

        def lte(self, *_args, **_kwargs):
            return self

        def order(self, *_args, **_kwargs):
            return self

        def limit(self, *_args, **_kwargs):
            return self

        def execute(self):
            if self.table_name == "tool_calls":
                return SimpleNamespace(
                    data=[
                        {
                            "id": 1,
                            "request_id": "r1",
                            "api_key_id": 10,
                            "tool_name": "notion_search",
                            "status": "success",
                            "error_code": None,
                            "latency_ms": 100,
                            "created_at": "2026-03-03T00:00:00+00:00",
                        }
                    ]
                )
            if self.table_name == "api_keys":
                return SimpleNamespace(data=[{"id": 10, "name": "prod", "key_prefix": "metel_prod"}])
            return SimpleNamespace(data=[])

    class _Client:
        def table(self, name: str):
            return _Query(name)

    async def _fake_user(_request: Request) -> str:
        return "user-1"

    monkeypatch.setattr("app.routes.audit.get_authenticated_user_id", _fake_user)
    monkeypatch.setattr("app.routes.audit.create_client", lambda *_args, **_kwargs: _Client())
    monkeypatch.setattr(
        "app.routes.audit.get_settings",
        lambda: SimpleNamespace(supabase_url="https://example.supabase.co", supabase_service_role_key="service-role-key"),
    )

    response = asyncio.run(
        export_audit_events(
            _request(),
            format="jsonl",
            limit=10,
            status="all",
            tool_name="",
            api_key_id=None,
            error_code="",
            from_="",
            to="",
        )
    )
    assert response.media_type == "application/x-ndjson"
    assert "audit-events.jsonl" in response.headers.get("Content-Disposition", "")
    body = response.body.decode("utf-8")
    assert "\"tool_name\": \"notion_search\"" in body
    assert "\"decision\": \"allowed\"" in body


def test_export_audit_events_csv(monkeypatch):
    class _Query:
        def __init__(self, table_name: str):
            self.table_name = table_name

        def select(self, *_args, **_kwargs):
            return self

        def eq(self, *_args, **_kwargs):
            return self

        def gte(self, *_args, **_kwargs):
            return self

        def lte(self, *_args, **_kwargs):
            return self

        def order(self, *_args, **_kwargs):
            return self

        def limit(self, *_args, **_kwargs):
            return self

        def execute(self):
            if self.table_name == "tool_calls":
                return SimpleNamespace(
                    data=[
                        {
                            "id": 2,
                            "request_id": "r2",
                            "api_key_id": 10,
                            "tool_name": "linear_list_issues",
                            "status": "fail",
                            "error_code": "policy_blocked",
                            "latency_ms": 50,
                            "created_at": "2026-03-03T00:01:00+00:00",
                        }
                    ]
                )
            if self.table_name == "api_keys":
                return SimpleNamespace(data=[{"id": 10, "name": "prod", "key_prefix": "metel_prod"}])
            return SimpleNamespace(data=[])

    class _Client:
        def table(self, name: str):
            return _Query(name)

    async def _fake_user(_request: Request) -> str:
        return "user-1"

    monkeypatch.setattr("app.routes.audit.get_authenticated_user_id", _fake_user)
    monkeypatch.setattr("app.routes.audit.create_client", lambda *_args, **_kwargs: _Client())
    monkeypatch.setattr(
        "app.routes.audit.get_settings",
        lambda: SimpleNamespace(supabase_url="https://example.supabase.co", supabase_service_role_key="service-role-key"),
    )

    response = asyncio.run(
        export_audit_events(
            _request(),
            format="csv",
            limit=10,
            status="all",
            tool_name="",
            api_key_id=None,
            error_code="",
            from_="",
            to="",
        )
    )
    assert response.media_type == "text/csv"
    assert "audit-events.csv" in response.headers.get("Content-Disposition", "")
    body = response.body.decode("utf-8")
    assert "tool_name,connector,status,decision,error_code" in body
    assert "linear_list_issues,,fail,policy_blocked,policy_blocked" in body


def test_export_audit_events_invalid_format_raises(monkeypatch):
    async def _fake_user(_request: Request) -> str:
        return "user-1"

    monkeypatch.setattr("app.routes.audit.get_authenticated_user_id", _fake_user)
    monkeypatch.setattr(
        "app.routes.audit.get_settings",
        lambda: SimpleNamespace(supabase_url="https://example.supabase.co", supabase_service_role_key="service-role-key"),
    )
    monkeypatch.setattr("app.routes.audit.create_client", lambda *_args, **_kwargs: SimpleNamespace(table=lambda _name: None))

    try:
        asyncio.run(
            export_audit_events(
                _request(),
                format="xml",
                limit=10,
                status="all",
                tool_name="",
                api_key_id=None,
                error_code="",
                from_="",
                to="",
            )
        )
    except HTTPException as exc:
        assert exc.status_code == 400
        assert exc.detail == "invalid_export_format"
    else:
        assert False, "expected HTTPException"


def test_list_audit_events_team_filter_without_keys_returns_empty(monkeypatch):
    class _Query:
        def __init__(self, table_name: str):
            self.table_name = table_name
            self.ops: list[tuple[str, str, object]] = []

        def select(self, *_args, **_kwargs):
            return self

        def eq(self, field: str, value):
            self.ops.append(("eq", field, value))
            return self

        def execute(self):
            if self.table_name == "api_keys":
                return SimpleNamespace(data=[])
            return SimpleNamespace(data=[])

    class _Client:
        def __init__(self):
            self.queries: list[str] = []

        def table(self, name: str):
            self.queries.append(name)
            return _Query(name)

    client = _Client()

    async def _fake_user(_request: Request) -> str:
        return "user-1"

    monkeypatch.setattr("app.routes.audit.get_authenticated_user_id", _fake_user)
    monkeypatch.setattr("app.routes.audit.create_client", lambda *_args, **_kwargs: client)
    monkeypatch.setattr(
        "app.routes.audit.get_settings",
        lambda: SimpleNamespace(supabase_url="https://example.supabase.co", supabase_service_role_key="service-role-key"),
    )

    out = asyncio.run(
        list_audit_events(
            _request(),
            limit=50,
            status="all",
            tool_name="",
            api_key_id=None,
            team_id=999,
            error_code="",
            connector="",
            decision="all",
            from_="",
            to="",
        )
    )

    assert out["count"] == 0
    assert "api_keys" in client.queries
    assert "tool_calls" not in client.queries


def test_list_audit_events_organization_filter_scopes_to_org_members(monkeypatch):
    class _Query:
        def __init__(self, client, table_name: str):
            self.client = client
            self.table_name = table_name
            self.ops: list[tuple[str, str, object]] = []

        def select(self, *_args, **_kwargs):
            return self

        def eq(self, field: str, value):
            self.ops.append(("eq", field, value))
            return self

        def in_(self, field: str, values):
            self.ops.append(("in", field, tuple(values)))
            return self

        def order(self, *_args, **_kwargs):
            return self

        def limit(self, *_args, **_kwargs):
            return self

        def execute(self):
            self.client.query_logs.append((self.table_name, list(self.ops)))
            if self.table_name == "org_memberships":
                has_owner_check = any(op == ("eq", "user_id", "user-1") for op in self.ops)
                if has_owner_check:
                    return SimpleNamespace(data=[{"organization_id": 1}])
                return SimpleNamespace(data=[{"user_id": "user-1"}, {"user_id": "user-2"}])
            if self.table_name == "tool_calls":
                return SimpleNamespace(data=[])
            if self.table_name == "api_keys":
                return SimpleNamespace(data=[])
            return SimpleNamespace(data=[])

    class _Client:
        def __init__(self):
            self.query_logs: list[tuple[str, list[tuple[str, str, object]]]] = []

        def table(self, name: str):
            return _Query(self, name)

    client = _Client()

    async def _fake_user(_request: Request) -> str:
        return "user-1"

    monkeypatch.setattr("app.routes.audit.get_authenticated_user_id", _fake_user)
    monkeypatch.setattr("app.routes.audit.create_client", lambda *_args, **_kwargs: client)
    monkeypatch.setattr(
        "app.routes.audit.get_settings",
        lambda: SimpleNamespace(supabase_url="https://example.supabase.co", supabase_service_role_key="service-role-key"),
    )

    out = asyncio.run(
        list_audit_events(
            _request(),
            limit=20,
            status="all",
            tool_name="",
            api_key_id=None,
            team_id=None,
            organization_id=1,
            error_code="",
            connector="",
            decision="all",
            from_="",
            to="",
        )
    )
    assert out["count"] == 0
    tool_calls_queries = [item for item in client.query_logs if item[0] == "tool_calls"]
    assert any(("in", "user_id", ("user-1", "user-2")) in ops for _, ops in tool_calls_queries)


def test_get_audit_event_detail(monkeypatch):
    class _Query:
        def __init__(self, table_name: str):
            self.table_name = table_name

        def select(self, *_args, **_kwargs):
            return self

        def eq(self, *_args, **_kwargs):
            return self

        def limit(self, *_args, **_kwargs):
            return self

        def execute(self):
            if self.table_name == "tool_calls":
                return SimpleNamespace(
                    data=[
                        {
                            "id": 7,
                            "request_id": "req-7",
                            "trace_id": "trace-7",
                            "api_key_id": 10,
                            "tool_name": "linear_list_issues",
                            "connector": "linear",
                            "status": "fail",
                            "error_code": "policy_blocked",
                            "latency_ms": 33,
                            "request_payload": {"token": "***"},
                            "resolved_payload": {"team_id": "a"},
                            "risk_result": {"allowed": False},
                            "upstream_status": None,
                            "retry_count": 0,
                            "backoff_ms": 250,
                            "masked_fields": ["token"],
                            "created_at": "2026-03-03T00:01:00+00:00",
                        }
                    ]
                )
            if self.table_name == "api_keys":
                return SimpleNamespace(data=[{"id": 10, "name": "prod", "key_prefix": "metel_prod"}])
            return SimpleNamespace(data=[])

    class _Client:
        def table(self, name: str):
            return _Query(name)

    async def _fake_user(_request: Request) -> str:
        return "user-1"

    monkeypatch.setattr("app.routes.audit.get_authenticated_user_id", _fake_user)
    monkeypatch.setattr("app.routes.audit.create_client", lambda *_args, **_kwargs: _Client())
    monkeypatch.setattr(
        "app.routes.audit.get_settings",
        lambda: SimpleNamespace(supabase_url="x", supabase_service_role_key="y"),
    )

    out = asyncio.run(get_audit_event_detail(_request(), event_id=7))
    assert out["id"] == 7
    assert out["trace_id"] == "trace-7"
    assert out["action"]["connector"] == "linear"
    assert out["execution"]["masked_fields"] == ["token"]
