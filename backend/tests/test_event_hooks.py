import asyncio
from types import SimpleNamespace

from app.core import event_hooks


class _UpdateQuery:
    def __init__(self, client, table_name: str, payload: dict):
        self.client = client
        self.table_name = table_name
        self.payload = payload
        self.filters: list[tuple[str, object]] = []

    def eq(self, field: str, value):
        self.filters.append((field, value))
        return self

    def execute(self):
        self.client.updates.append((self.table_name, dict(self.payload), list(self.filters)))
        return SimpleNamespace(data=[self.payload])


class _SelectQuery:
    def __init__(self, client, table_name: str):
        self.client = client
        self.table_name = table_name
        self.filters: list[tuple[str, object]] = []

    def eq(self, field: str, value):
        self.filters.append((field, value))
        return self

    def in_(self, *_args, **_kwargs):
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def execute(self):
        self.client.selects.append((self.table_name, list(self.filters)))
        if self.table_name == "webhook_deliveries":
            return SimpleNamespace(data=self.client.delivery_rows)
        if self.table_name == "webhook_subscriptions":
            return SimpleNamespace(data=self.client.subscription_rows)
        return SimpleNamespace(data=[])


class _Client:
    def __init__(self, *, delivery_rows=None, subscription_rows=None):
        self.delivery_rows = delivery_rows or []
        self.subscription_rows = subscription_rows or []
        self.updates: list[tuple[str, dict, list[tuple[str, object]]]] = []
        self.selects: list[tuple[str, list[tuple[str, object]]]] = []

    def table(self, table_name: str):
        client = self

        class _Table:
            def select(self, *_args, **_kwargs):
                return _SelectQuery(client, table_name)

            def update(self, payload: dict):
                return _UpdateQuery(client, table_name, payload)

        return _Table()


def test_attempt_delivery_marks_dead_letter_after_retry_exhausted(monkeypatch):
    async def _fake_deliver_http(**_kwargs):
        return "failed", 500, "http_500"

    monkeypatch.setattr("app.core.event_hooks._deliver_http", _fake_deliver_http)
    client = _Client()
    out = asyncio.run(
        event_hooks._attempt_delivery(
            supabase=client,
            delivery_id=1,
            subscription={"id": 10, "endpoint_url": "https://example.com/hook", "secret": "x"},
            event_type="tool_failed",
            delivery_payload={"x": 1},
            retry_count=3,
            max_retries=3,
            base_backoff_seconds=30,
            max_backoff_seconds=900,
        )
    )
    assert out["status"] == "dead_letter"
    assert str(out["error_message"]).startswith("max_retries_exceeded:")
    assert out["next_retry_at"] is None


def test_retry_webhook_delivery_inactive_subscription_sets_dead_letter():
    client = _Client(
        delivery_rows=[{"id": 7, "subscription_id": 3, "event_type": "tool_called", "payload": {"ok": True}, "retry_count": 1}],
        subscription_rows=[{"id": 3, "endpoint_url": "https://example.com", "secret": None, "is_active": False}],
    )
    out = asyncio.run(
        event_hooks.retry_webhook_delivery(
            supabase=client,
            user_id="user-1",
            delivery_id=7,
            max_retries=3,
            base_backoff_seconds=30,
            max_backoff_seconds=900,
        )
    )
    assert out is not None
    assert out["status"] == "dead_letter"
    assert out["error_message"] == "subscription_inactive"


def test_process_pending_webhook_retries_counts_dead_letter(monkeypatch):
    async def _fake_retry_webhook_delivery(**_kwargs):
        return {"status": "dead_letter"}

    monkeypatch.setattr("app.core.event_hooks.retry_webhook_delivery", _fake_retry_webhook_delivery)
    client = _Client(
        delivery_rows=[
            {
                "id": 1,
                "user_id": "user-1",
                "subscription_id": 10,
                "event_type": "tool_failed",
                "payload": {},
                "retry_count": 3,
                "next_retry_at": None,
                "status": "retrying",
            }
        ]
    )
    out = asyncio.run(
        event_hooks.process_pending_webhook_retries(
            supabase=client,
            user_id="user-1",
            limit=100,
            max_retries=3,
            base_backoff_seconds=30,
            max_backoff_seconds=900,
        )
    )
    assert out["processed"] == 1
    assert out["dead_lettered"] == 1
    assert out["failed"] == 0
