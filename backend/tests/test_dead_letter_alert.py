import asyncio

from app.core.dead_letter_alert import send_dead_letter_alert


class _Resp:
    def __init__(self, status_code: int):
        self.status_code = status_code


class _Client:
    def __init__(self, capture: dict):
        self.capture = capture
        self.capture.setdefault("posts", [])

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, json):
        self.capture["url"] = url
        self.capture["json"] = json
        self.capture["posts"].append({"url": url, "json": json})
        return _Resp(200)


def test_send_dead_letter_alert_slack_payload_uses_text(monkeypatch):
    capture: dict = {}
    monkeypatch.setattr("app.core.dead_letter_alert.httpx.AsyncClient", lambda timeout=5.0: _Client(capture))

    ok = asyncio.run(
        send_dead_letter_alert(
            webhook_url="https://hooks.slack.com/services/T/A/B",
            user_id="u1",
            source="process_retries",
            dead_lettered=1,
            details={"x": 1},
        )
    )

    assert ok is True
    assert capture["url"].startswith("https://hooks.slack.com/services/")
    assert "text" in capture["json"]
    assert "dead-letter alert" in capture["json"]["text"]


def test_send_dead_letter_alert_generic_payload_keeps_structured_json(monkeypatch):
    capture: dict = {}
    monkeypatch.setattr("app.core.dead_letter_alert.httpx.AsyncClient", lambda timeout=5.0: _Client(capture))

    ok = asyncio.run(
        send_dead_letter_alert(
            webhook_url="https://example.com/webhook",
            user_id="u1",
            source="process_retries",
            dead_lettered=2,
            details={"x": 2},
        )
    )

    assert ok is True
    assert capture["json"]["event"] == "dead_letter_alert"
    assert capture["json"]["dead_lettered"] == 2


def test_send_dead_letter_alert_posts_ticket_payload_when_configured(monkeypatch):
    capture: dict = {}
    monkeypatch.setattr("app.core.dead_letter_alert.httpx.AsyncClient", lambda timeout=5.0: _Client(capture))

    ok = asyncio.run(
        send_dead_letter_alert(
            webhook_url="https://example.com/slack-like",
            user_id="u1",
            source="scheduler_process_retries",
            dead_lettered=3,
            details={"delivery_id": 9},
            ticket_webhook_url="https://example.com/ticket",
        )
    )

    assert ok is True
    assert len(capture["posts"]) == 2
    assert capture["posts"][1]["url"] == "https://example.com/ticket"
    assert capture["posts"][1]["json"]["event"] == "dead_letter_alert"
