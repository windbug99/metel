import asyncio
from types import SimpleNamespace

from fastapi import HTTPException
from starlette.requests import Request

from app.routes.integrations import process_deliveries, retry_delivery


def _request(path: str) -> Request:
    scope = {"type": "http", "method": "POST", "path": path, "headers": []}
    return Request(scope)


def test_process_deliveries_calls_retry_processor(monkeypatch):
    async def _fake_user(_request: Request) -> str:
        return "user-1"

    async def _fake_process(**kwargs):
        assert kwargs["user_id"] == "user-1"
        assert kwargs["limit"] == 50
        return {"processed": 3, "succeeded": 2, "failed": 1, "skipped": 0}

    monkeypatch.setattr("app.routes.integrations.get_authenticated_user_id", _fake_user)
    monkeypatch.setattr("app.routes.integrations.create_client", lambda *_args, **_kwargs: SimpleNamespace())
    monkeypatch.setattr(
        "app.routes.integrations.get_settings",
        lambda: SimpleNamespace(
            supabase_url="https://example.supabase.co",
            supabase_service_role_key="service-role-key",
            webhook_retry_max_retries=5,
            webhook_retry_base_backoff_seconds=30,
            webhook_retry_max_backoff_seconds=900,
        ),
    )
    monkeypatch.setattr("app.routes.integrations.process_pending_webhook_retries", _fake_process)

    out = asyncio.run(process_deliveries(_request("/api/integrations/deliveries/process-retries"), limit=50))
    assert out["ok"] is True
    assert out["processed"] == 3
    assert out["succeeded"] == 2
    assert out["failed"] == 1


def test_process_deliveries_sends_dead_letter_alert(monkeypatch):
    async def _fake_user(_request: Request) -> str:
        return "user-1"

    async def _fake_process(**kwargs):
        assert kwargs["user_id"] == "user-1"
        return {"processed": 1, "succeeded": 0, "failed": 0, "dead_lettered": 1, "skipped": 0}

    called: dict[str, object] = {}

    async def _fake_alert(**kwargs):
        called.update(kwargs)
        return True

    monkeypatch.setattr("app.routes.integrations.get_authenticated_user_id", _fake_user)
    monkeypatch.setattr("app.routes.integrations.create_client", lambda *_args, **_kwargs: SimpleNamespace())
    monkeypatch.setattr(
        "app.routes.integrations.get_settings",
        lambda: SimpleNamespace(
            supabase_url="https://example.supabase.co",
            supabase_service_role_key="service-role-key",
            webhook_retry_max_retries=5,
            webhook_retry_base_backoff_seconds=30,
            webhook_retry_max_backoff_seconds=900,
            dead_letter_alert_webhook_url="https://hooks.example/abc",
            dead_letter_alert_min_count=1,
        ),
    )
    monkeypatch.setattr("app.routes.integrations.process_pending_webhook_retries", _fake_process)
    monkeypatch.setattr("app.routes.integrations.send_dead_letter_alert", _fake_alert)

    out = asyncio.run(process_deliveries(_request("/api/integrations/deliveries/process-retries"), limit=20))
    assert out["ok"] is True
    assert out["dead_lettered"] == 1
    assert called.get("source") == "process_retries"
    assert called.get("dead_lettered") == 1


def test_retry_delivery_not_found(monkeypatch):
    async def _fake_user(_request: Request) -> str:
        return "user-1"

    async def _fake_retry(**_kwargs):
        return None

    monkeypatch.setattr("app.routes.integrations.get_authenticated_user_id", _fake_user)
    monkeypatch.setattr("app.routes.integrations.create_client", lambda *_args, **_kwargs: SimpleNamespace())
    monkeypatch.setattr(
        "app.routes.integrations.get_settings",
        lambda: SimpleNamespace(
            supabase_url="https://example.supabase.co",
            supabase_service_role_key="service-role-key",
            webhook_retry_max_retries=5,
            webhook_retry_base_backoff_seconds=30,
            webhook_retry_max_backoff_seconds=900,
        ),
    )
    monkeypatch.setattr("app.routes.integrations.retry_webhook_delivery", _fake_retry)

    try:
        asyncio.run(retry_delivery(_request("/api/integrations/deliveries/999/retry"), "999"))
    except HTTPException as exc:
        assert exc.status_code == 404
        assert exc.detail == "delivery_not_found"
    else:
        assert False, "expected HTTPException"


def test_retry_delivery_sends_dead_letter_alert(monkeypatch):
    async def _fake_user(_request: Request) -> str:
        return "user-1"

    async def _fake_retry(**_kwargs):
        return {"status": "dead_letter", "error_message": "max_retries_exceeded:http_500"}

    called: dict[str, object] = {}

    async def _fake_alert(**kwargs):
        called.update(kwargs)
        return True

    monkeypatch.setattr("app.routes.integrations.get_authenticated_user_id", _fake_user)
    monkeypatch.setattr("app.routes.integrations.create_client", lambda *_args, **_kwargs: SimpleNamespace())
    monkeypatch.setattr(
        "app.routes.integrations.get_settings",
        lambda: SimpleNamespace(
            supabase_url="https://example.supabase.co",
            supabase_service_role_key="service-role-key",
            webhook_retry_max_retries=5,
            webhook_retry_base_backoff_seconds=30,
            webhook_retry_max_backoff_seconds=900,
            dead_letter_alert_webhook_url="https://hooks.example/abc",
            dead_letter_alert_min_count=1,
        ),
    )
    monkeypatch.setattr("app.routes.integrations.retry_webhook_delivery", _fake_retry)
    monkeypatch.setattr("app.routes.integrations.send_dead_letter_alert", _fake_alert)

    out = asyncio.run(retry_delivery(_request("/api/integrations/deliveries/42/retry"), "42"))
    assert out["ok"] is True
    assert str(out["result"].get("status")) == "dead_letter"
    assert called.get("source") == "manual_retry"
    assert called.get("dead_lettered") == 1
