import asyncio
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

from starlette.requests import Request

from app.routes.canva import (
    CanvaAssetUrlUploadCreateRequest,
    CanvaCommentReplyCreateRequest,
    CanvaCommentThreadCreateRequest,
    CanvaDesignCreateRequest,
    CanvaExportCreateRequest,
    CanvaFolderCreateRequest,
    CanvaFolderMoveRequest,
    CanvaResizeCreateRequest,
    CanvaUrlImportCreateRequest,
    canva_asset_get,
    canva_brand_template_dataset_get,
    canva_brand_template_get,
    canva_brand_templates_list,
    canva_comment_replies_list,
    canva_comment_reply_create,
    canva_comment_thread_create,
    canva_comment_thread_get,
    canva_design_create,
    canva_design_export_formats,
    canva_design_get,
    canva_designs_list,
    canva_export_create,
    canva_export_get,
    canva_folder_create,
    canva_folder_items_list,
    canva_folder_move,
    canva_folder_search,
    canva_oauth_callback,
    canva_oauth_start,
    canva_oauth_status,
    canva_resize_create,
    canva_resize_get,
    canva_url_asset_upload_create,
    canva_url_asset_upload_get,
    canva_url_import_create,
    canva_url_import_get,
)


def _request(path: str, method: str = "GET") -> Request:
    scope = {"type": "http", "method": method, "path": path, "query_string": b"", "headers": []}
    return Request(scope)


class _Query:
    def __init__(self, client, table_name: str):
        self.client = client
        self.table_name = table_name
        self.filters: list[tuple[str, object]] = []
        self.payload = None
        self.operation = "select"

    def select(self, *_args, **_kwargs):
        self.operation = "select"
        return self

    def eq(self, field: str, value):
        self.filters.append((field, value))
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def maybe_single(self):
        return self

    def upsert(self, payload, **_kwargs):
        self.operation = "upsert"
        self.payload = payload
        return self

    def delete(self):
        self.operation = "delete"
        return self

    def execute(self):
        if self.table_name == "oauth_pending_states":
            if self.operation == "upsert":
                self.client.pending_rows[self.payload["state"]] = dict(self.payload)
                return SimpleNamespace(data=[dict(self.payload)])
            if self.operation == "delete":
                state = None
                for field, value in self.filters:
                    if field == "state":
                        state = value
                if state is not None:
                    self.client.pending_rows.pop(str(state), None)
                return SimpleNamespace(data=[])
            state = None
            provider = None
            for field, value in self.filters:
                if field == "state":
                    state = value
                if field == "provider":
                    provider = value
            row = self.client.pending_rows.get(str(state))
            if row and (provider is None or row.get("provider") == provider):
                return SimpleNamespace(data=[dict(row)])
            return SimpleNamespace(data=[])

        if self.table_name == "oauth_tokens":
            if self.operation == "upsert":
                key = (self.payload["user_id"], self.payload["provider"])
                self.client.oauth_rows[key] = dict(self.payload)
                return SimpleNamespace(data=[dict(self.payload)])
            rows = list(self.client.oauth_rows.values())
            for field, value in self.filters:
                rows = [row for row in rows if row.get(field) == value]
            if getattr(self, "operation", "select") == "delete":
                for row in rows:
                    key = (row["user_id"], row["provider"])
                    self.client.oauth_rows.pop(key, None)
                return SimpleNamespace(data=[])
            if rows:
                return SimpleNamespace(data=dict(rows[0]) if any(True for _ in [1]) else None)
            return SimpleNamespace(data=None)

        return SimpleNamespace(data=[])


class _Client:
    def __init__(self):
        self.pending_rows: dict[str, dict] = {}
        self.oauth_rows: dict[tuple[str, str], dict] = {}

    def table(self, name: str):
        return _Query(self, name)


class _Response:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


class _AsyncClient:
    def __init__(self, responses: list[_Response]):
        self._responses = responses

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, *_args, **_kwargs):
        return self._responses.pop(0)

    async def get(self, *_args, **_kwargs):
        return self._responses.pop(0)

    async def request(self, *_args, **_kwargs):
        return self._responses.pop(0)


def test_canva_oauth_start_builds_pkce_url_and_persists_state(monkeypatch):
    client = _Client()

    async def _fake_user(_request: Request) -> str:
        return "user-1"

    monkeypatch.setattr("app.routes.canva.get_authenticated_user_id", _fake_user)
    monkeypatch.setattr("app.routes.canva.create_client", lambda *_args, **_kwargs: client)
    monkeypatch.setattr(
        "app.routes.canva.get_settings",
        lambda: SimpleNamespace(
            canva_client_id="canva-client",
            canva_client_secret="canva-secret",
            canva_redirect_uri="https://api.example.com/api/oauth/canva/callback",
            canva_state_secret="state-secret",
            canva_scopes="profile:read design:meta:read design:content:read design:content:write asset:read asset:write folder:read folder:write",
            canva_api_base_url="https://api.canva.com/rest/v1",
            canva_oauth_authorize_url="https://www.canva.com/api/oauth/authorize",
            frontend_url="https://app.example.com",
            supabase_url="x",
            supabase_service_role_key="y",
            canva_token_encryption_key=None,
            notion_token_encryption_key=None,
        ),
    )

    out = asyncio.run(canva_oauth_start(_request("/api/oauth/canva/start", "POST")))
    parsed = urlparse(out["auth_url"])
    query = parse_qs(parsed.query)

    assert out["ok"] is True
    assert parsed.scheme == "https"
    assert query["client_id"] == ["canva-client"]
    # Connect flow stays on the minimum stable scope set even if broader
    # feature scopes are configured in env.
    assert query["scope"] == ["profile:read design:meta:read"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["state"][0] in client.pending_rows
    assert client.pending_rows[query["state"][0]]["provider"] == "canva"


def test_canva_oauth_callback_persists_tokens_and_identity(monkeypatch):
    client = _Client()
    pending_state = "dXNlci0xOjQxMDAwMDAwMDA6YTBjNWVjMWE0NTEzNGE4YTRjZjFjMzBlMzQ5NWI3NzQ4YTA2M2Q4NjIwY2M4NDk4ZDJhNjUyM2IzOWVjNTlkMQ=="
    client.pending_rows[pending_state] = {
        "state": pending_state,
        "user_id": "user-1",
        "provider": "canva",
        "code_verifier": "verifier-123",
        "expires_at": "2999-01-01T00:00:00+00:00",
    }

    monkeypatch.setattr("app.routes.canva.create_client", lambda *_args, **_kwargs: client)
    monkeypatch.setattr(
        "app.routes.canva.get_settings",
        lambda: SimpleNamespace(
            canva_client_id="canva-client",
            canva_client_secret="canva-secret",
            canva_redirect_uri="https://api.example.com/api/oauth/canva/callback",
            canva_state_secret="state-secret",
            canva_scopes="profile:read design:meta:read",
            canva_api_base_url="https://api.canva.com/rest/v1",
            canva_oauth_authorize_url="https://www.canva.com/api/oauth/authorize",
            frontend_url="https://app.example.com",
            supabase_url="x",
            supabase_service_role_key="y",
            canva_token_encryption_key=None,
            notion_token_encryption_key=None,
        ),
    )
    monkeypatch.setattr("app.routes.canva.verify_state", lambda **_kwargs: "user-1")
    monkeypatch.setattr(
        "app.routes.canva.httpx.AsyncClient",
        lambda **_kwargs: _AsyncClient(
            [
                _Response(200, {"access_token": "access-1", "refresh_token": "refresh-1", "expires_in": 3600, "scope": "profile:read design:meta:read"}),
                _Response(200, {"user": {"user_id": "canva-user-1", "team_id": "team-9"}}),
                _Response(200, {"profile": {"display_name": "Canva User"}}),
                _Response(200, {"capabilities": {"resize": {"supported": True}}}),
            ]
        ),
    )

    out = asyncio.run(canva_oauth_callback(code="code-1", state=pending_state))
    row = client.oauth_rows[("user-1", "canva")]

    assert out.status_code == 302
    assert row["workspace_id"] == "canva-user-1"
    assert row["workspace_name"] == "Canva User"
    assert row["provider_team_id"] == "team-9"
    assert row["refresh_token_encrypted"] == "refresh-1"
    assert row["provider_metadata"]["capabilities"]["resize"]["supported"] is True


def test_canva_oauth_status_returns_connection(monkeypatch):
    client = _Client()
    client.oauth_rows[("user-1", "canva")] = {
        "user_id": "user-1",
        "provider": "canva",
        "workspace_name": "Canva User",
        "workspace_id": "canva-user-1",
        "provider_team_id": "team-9",
        "updated_at": "2026-03-11T00:00:00+00:00",
        "token_expires_at": "2026-03-11T01:00:00+00:00",
        "provider_metadata": {"capabilities": {"resize": {"supported": True}}},
    }

    async def _fake_user(_request: Request) -> str:
        return "user-1"

    monkeypatch.setattr("app.routes.canva.get_authenticated_user_id", _fake_user)
    monkeypatch.setattr("app.routes.canva.create_client", lambda *_args, **_kwargs: client)
    monkeypatch.setattr(
        "app.routes.canva.get_settings",
        lambda: SimpleNamespace(supabase_url="x", supabase_service_role_key="y"),
    )

    out = asyncio.run(canva_oauth_status(_request("/api/oauth/canva/status")))
    assert out["connected"] is True
    assert out["integration"]["workspace_name"] == "Canva User"


def test_canva_designs_list_returns_items(monkeypatch):
    async def _fake_user(_request: Request) -> str:
        return "user-1"

    monkeypatch.setattr("app.routes.canva.get_authenticated_user_id", _fake_user)
    monkeypatch.setattr("app.routes.canva._require_canva_access_token", lambda _user_id: asyncio.sleep(0, result="token-1"))
    monkeypatch.setattr(
        "app.routes.canva.httpx.AsyncClient",
        lambda **_kwargs: _AsyncClient(
            [
                _Response(
                    200,
                    {
                        "items": [
                            {"id": "design-1", "title": "Launch banner"},
                            {"id": "design-2", "title": "Quarterly report"},
                        ],
                        "continuation": "cursor-1",
                    },
                )
            ]
        ),
    )
    monkeypatch.setattr(
        "app.routes.canva.get_settings",
        lambda: SimpleNamespace(canva_api_base_url="https://api.canva.com/rest/v1"),
    )

    out = asyncio.run(canva_designs_list(_request("/api/oauth/canva/designs"), limit=2))
    assert out["ok"] is True
    assert out["count"] == 2
    assert out["continuation"] == "cursor-1"


def test_canva_design_create_returns_design(monkeypatch):
    async def _fake_user(_request: Request) -> str:
        return "user-1"

    monkeypatch.setattr("app.routes.canva.get_authenticated_user_id", _fake_user)
    monkeypatch.setattr("app.routes.canva._require_canva_access_token", lambda _user_id: asyncio.sleep(0, result="token-1"))
    monkeypatch.setattr(
        "app.routes.canva.httpx.AsyncClient",
        lambda **_kwargs: _AsyncClient(
            [_Response(200, {"design": {"id": "design-1", "title": "Poster", "edit_url": "https://www.canva.com/design/1/edit"}})]
        ),
    )
    monkeypatch.setattr(
        "app.routes.canva.get_settings",
        lambda: SimpleNamespace(canva_api_base_url="https://api.canva.com/rest/v1"),
    )

    out = asyncio.run(
        canva_design_create(
            _request("/api/oauth/canva/designs", "POST"),
            CanvaDesignCreateRequest(title="Poster", design_type={"type": "poster"}),
        )
    )
    assert out["ok"] is True
    assert out["design"]["id"] == "design-1"


def test_canva_export_endpoints_return_job(monkeypatch):
    async def _fake_user(_request: Request) -> str:
        return "user-1"

    monkeypatch.setattr("app.routes.canva.get_authenticated_user_id", _fake_user)
    monkeypatch.setattr("app.routes.canva._require_canva_access_token", lambda _user_id: asyncio.sleep(0, result="token-1"))
    monkeypatch.setattr(
        "app.routes.canva.httpx.AsyncClient",
        lambda **_kwargs: _AsyncClient(
            [
                _Response(200, {"job": {"id": "export-1", "status": "in_progress"}}),
                _Response(200, {"job": {"id": "export-1", "status": "success", "urls": ["https://download.example.com/file.pdf"]}}),
                _Response(200, {"formats": [{"type": "pdf"}, {"type": "png"}]}),
                _Response(200, {"design": {"id": "design-1", "title": "Poster"}}),
            ]
        ),
    )
    monkeypatch.setattr(
        "app.routes.canva.get_settings",
        lambda: SimpleNamespace(canva_api_base_url="https://api.canva.com/rest/v1"),
    )

    create_out = asyncio.run(
        canva_export_create(
            _request("/api/oauth/canva/exports", "POST"),
            CanvaExportCreateRequest(design_id="design-1", format={"type": "pdf"}),
        )
    )
    get_out = asyncio.run(canva_export_get(_request("/api/oauth/canva/exports/export-1"), export_id="export-1"))
    formats_out = asyncio.run(canva_design_export_formats(_request("/api/oauth/canva/designs/design-1/export-formats"), design_id="design-1"))
    design_out = asyncio.run(canva_design_get(_request("/api/oauth/canva/designs/design-1"), design_id="design-1"))

    assert create_out["job"]["id"] == "export-1"
    assert get_out["job"]["status"] == "success"
    assert formats_out["count"] == 2
    assert design_out["design"]["id"] == "design-1"


def test_canva_folder_endpoints_return_items_and_mutations(monkeypatch):
    async def _fake_user(_request: Request) -> str:
        return "user-1"

    monkeypatch.setattr("app.routes.canva.get_authenticated_user_id", _fake_user)
    monkeypatch.setattr("app.routes.canva._require_canva_access_token", lambda _user_id: asyncio.sleep(0, result="token-1"))
    monkeypatch.setattr(
        "app.routes.canva.httpx.AsyncClient",
        lambda **_kwargs: _AsyncClient(
            [
                _Response(
                    200,
                    {
                        "items": [
                            {"type": "folder", "folder": {"id": "folder-1", "name": "Campaigns"}},
                            {"type": "design", "design": {"id": "design-1", "title": "Poster"}},
                        ],
                        "continuation": "cursor-folders",
                    },
                ),
                _Response(
                    200,
                    {
                        "items": [
                            {"type": "folder", "folder": {"id": "folder-1", "name": "Campaigns"}},
                            {"type": "folder", "folder": {"id": "folder-2", "name": "Archive"}},
                        ],
                        "continuation": None,
                    },
                ),
                _Response(200, {"folder": {"id": "folder-3", "name": "Launch"}}),
                _Response(200, {"success": True}),
            ]
        ),
    )
    monkeypatch.setattr(
        "app.routes.canva.get_settings",
        lambda: SimpleNamespace(canva_api_base_url="https://api.canva.com/rest/v1"),
    )

    list_out = asyncio.run(canva_folder_items_list(_request("/api/oauth/canva/folders/root/items"), folder_id="root", item_types="folder,design"))
    search_out = asyncio.run(canva_folder_search(_request("/api/oauth/canva/folders/search"), folder_id="root", query="camp"))
    create_out = asyncio.run(
        canva_folder_create(
            _request("/api/oauth/canva/folders", "POST"),
            CanvaFolderCreateRequest(name="Launch", parent_folder_id="root"),
        )
    )
    move_out = asyncio.run(
        canva_folder_move(
            _request("/api/oauth/canva/folders/move", "POST"),
            CanvaFolderMoveRequest(item_id="design-1", to_folder_id="folder-3"),
        )
    )

    assert list_out["count"] == 2
    assert list_out["continuation"] == "cursor-folders"
    assert search_out["count"] == 1
    assert search_out["items"][0]["folder"]["id"] == "folder-1"
    assert create_out["folder"]["id"] == "folder-3"
    assert move_out["ok"] is True


def test_canva_asset_import_and_resize_endpoints_return_jobs(monkeypatch):
    async def _fake_user(_request: Request) -> str:
        return "user-1"

    monkeypatch.setattr("app.routes.canva.get_authenticated_user_id", _fake_user)
    monkeypatch.setattr("app.routes.canva._require_canva_access_token", lambda _user_id: asyncio.sleep(0, result="token-1"))
    monkeypatch.setattr(
        "app.routes.canva.httpx.AsyncClient",
        lambda **_kwargs: _AsyncClient(
            [
                _Response(200, {"asset": {"id": "asset-1", "name": "Brand Logo"}}),
                _Response(200, {"job": {"id": "asset-job-1", "status": "in_progress"}}),
                _Response(200, {"job": {"id": "asset-job-1", "status": "success", "asset": {"id": "asset-1"}}}),
                _Response(200, {"job": {"id": "import-job-1", "status": "in_progress"}}),
                _Response(200, {"job": {"id": "import-job-1", "status": "success", "design": {"id": "design-9"}}}),
                _Response(200, {"job": {"id": "resize-job-1", "status": "in_progress"}}),
                _Response(200, {"job": {"id": "resize-job-1", "status": "success", "design": {"id": "design-10"}}}),
            ]
        ),
    )
    monkeypatch.setattr(
        "app.routes.canva.get_settings",
        lambda: SimpleNamespace(canva_api_base_url="https://api.canva.com/rest/v1"),
    )

    asset_out = asyncio.run(canva_asset_get(_request("/api/oauth/canva/assets/asset-1"), asset_id="asset-1"))
    asset_upload_create_out = asyncio.run(
        canva_url_asset_upload_create(
            _request("/api/oauth/canva/url-asset-uploads", "POST"),
            CanvaAssetUrlUploadCreateRequest(name="Brand Logo", url="https://cdn.example.com/logo.png"),
        )
    )
    asset_upload_get_out = asyncio.run(canva_url_asset_upload_get(_request("/api/oauth/canva/url-asset-uploads/asset-job-1"), job_id="asset-job-1"))
    import_create_out = asyncio.run(
        canva_url_import_create(
            _request("/api/oauth/canva/url-imports", "POST"),
            CanvaUrlImportCreateRequest(title="Sales Deck", url="https://cdn.example.com/deck.pdf", mime_type="application/pdf"),
        )
    )
    import_get_out = asyncio.run(canva_url_import_get(_request("/api/oauth/canva/url-imports/import-job-1"), job_id="import-job-1"))
    resize_create_out = asyncio.run(
        canva_resize_create(
            _request("/api/oauth/canva/resizes", "POST"),
            CanvaResizeCreateRequest(design_id="design-9", design_type={"type": "presentation"}),
        )
    )
    resize_get_out = asyncio.run(canva_resize_get(_request("/api/oauth/canva/resizes/resize-job-1"), job_id="resize-job-1"))

    assert asset_out["asset"]["id"] == "asset-1"
    assert asset_upload_create_out["job"]["id"] == "asset-job-1"
    assert asset_upload_get_out["job"]["asset"]["id"] == "asset-1"
    assert import_create_out["job"]["id"] == "import-job-1"
    assert import_get_out["job"]["design"]["id"] == "design-9"
    assert resize_create_out["job"]["id"] == "resize-job-1"
    assert resize_get_out["job"]["design"]["id"] == "design-10"


def test_canva_comment_and_brand_template_endpoints_return_payloads(monkeypatch):
    async def _fake_user(_request: Request) -> str:
        return "user-1"

    monkeypatch.setattr("app.routes.canva.get_authenticated_user_id", _fake_user)
    monkeypatch.setattr("app.routes.canva._require_canva_access_token", lambda _user_id: asyncio.sleep(0, result="token-1"))
    monkeypatch.setattr(
        "app.routes.canva.httpx.AsyncClient",
        lambda **_kwargs: _AsyncClient(
            [
                _Response(200, {"thread": {"id": "thread-1", "message_plaintext": "Please review"}}),
                _Response(200, {"thread": {"id": "thread-1", "message_plaintext": "Please review"}}),
                _Response(200, {"reply": {"id": "reply-1", "message_plaintext": "Looks good"}}),
                _Response(200, {"replies": [{"id": "reply-1", "message_plaintext": "Looks good"}]}),
                _Response(200, {"items": [{"id": "bt-1", "title": "Sales Deck Template"}], "continuation": "cursor-bt"}),
                _Response(200, {"brand_template": {"id": "bt-1", "title": "Sales Deck Template"}}),
                _Response(200, {"dataset": {"fields": [{"name": "title", "type": "text"}]}}),
            ]
        ),
    )
    monkeypatch.setattr(
        "app.routes.canva.get_settings",
        lambda: SimpleNamespace(canva_api_base_url="https://api.canva.com/rest/v1"),
    )

    thread_create_out = asyncio.run(
        canva_comment_thread_create(
            _request("/api/oauth/canva/designs/design-1/comments", "POST"),
            design_id="design-1",
            body=CanvaCommentThreadCreateRequest(message_plaintext="Please review"),
        )
    )
    thread_get_out = asyncio.run(canva_comment_thread_get(_request("/api/oauth/canva/designs/design-1/comments/thread-1"), design_id="design-1", thread_id="thread-1"))
    reply_create_out = asyncio.run(
        canva_comment_reply_create(
            _request("/api/oauth/canva/designs/design-1/comments/thread-1/replies", "POST"),
            design_id="design-1",
            thread_id="thread-1",
            body=CanvaCommentReplyCreateRequest(message_plaintext="Looks good"),
        )
    )
    replies_out = asyncio.run(canva_comment_replies_list(_request("/api/oauth/canva/designs/design-1/comments/thread-1/replies"), design_id="design-1", thread_id="thread-1"))
    brand_templates_out = asyncio.run(canva_brand_templates_list(_request("/api/oauth/canva/brand-templates"), query="sales"))
    brand_template_out = asyncio.run(canva_brand_template_get(_request("/api/oauth/canva/brand-templates/bt-1"), brand_template_id="bt-1"))
    dataset_out = asyncio.run(canva_brand_template_dataset_get(_request("/api/oauth/canva/brand-templates/bt-1/dataset"), brand_template_id="bt-1"))

    assert thread_create_out["thread"]["id"] == "thread-1"
    assert thread_get_out["thread"]["id"] == "thread-1"
    assert reply_create_out["reply"]["id"] == "reply-1"
    assert replies_out["count"] == 1
    assert brand_templates_out["count"] == 1
    assert brand_templates_out["continuation"] == "cursor-bt"
    assert brand_template_out["brand_template"]["id"] == "bt-1"
    assert dataset_out["dataset"]["fields"][0]["name"] == "title"
