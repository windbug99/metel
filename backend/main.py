import logging
import uuid
import json

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from agent.registry import ToolSpecValidationError, validate_registry_on_startup
from app.core.config import get_settings
from app.routes.linear import router as linear_router
from app.routes.notion import router as notion_router
from app.routes.spotify import router as spotify_router
from app.routes.google import router as google_router
from app.routes.telegram import router as telegram_router

settings = get_settings()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("metel-backend")

app = FastAPI(title="metel backend", version="0.1.0")


def _normalize_origin(value: str) -> str:
    # Accept env values with quotes/brackets/trailing slash.
    return value.strip().strip("\"'").rstrip("/")


def _parse_allowed_origins(raw: str, fallback_frontend_url: str) -> list[str]:
    text = (raw or "").strip()
    parsed: list[str] = []

    # 1) JSON array form: ["https://a.com","https://b.com"]
    if text.startswith("[") and text.endswith("]"):
        try:
            items = json.loads(text)
            if isinstance(items, list):
                parsed.extend(str(item) for item in items if isinstance(item, str))
        except Exception:
            pass

    # 2) Comma/newline separated form.
    if not parsed:
        normalized_text = text.replace("\n", ",")
        parsed.extend(part for part in normalized_text.split(",") if part.strip())

    # 3) Ensure frontend_url is always included as fallback.
    if fallback_frontend_url:
        parsed.append(fallback_frontend_url)

    origins: list[str] = []
    seen: set[str] = set()
    for item in parsed:
        origin = _normalize_origin(item)
        if not origin or origin in seen:
            continue
        seen.add(origin)
        origins.append(origin)
    return origins


origins = _parse_allowed_origins(settings.allowed_origins, settings.frontend_url)
logger.info("cors_allowed_origins=%s", origins)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def validate_tool_specs() -> None:
    if not settings.tool_specs_validate_on_startup:
        logger.info("tool_specs_validation skipped (TOOL_SPECS_VALIDATE_ON_STARTUP=false)")
        return
    try:
        summary = validate_registry_on_startup()
        logger.info(
            "tool_specs_validation ok service_count=%s tool_count=%s",
            summary["service_count"],
            summary["tool_count"],
        )
    except ToolSpecValidationError as exc:
        logger.exception("tool_specs_validation failed")
        raise RuntimeError(f"Tool spec validation failed: {exc}") from exc


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    request_id = getattr(request.state, "request_id", "unknown")
    logger.warning("http_error request_id=%s path=%s detail=%s", request_id, request.url.path, exc.detail)
    message = exc.detail if isinstance(exc.detail, str) else "요청 처리 중 오류가 발생했습니다."
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"message": message, "request_id": request_id}},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", "unknown")
    logger.exception("unhandled_error request_id=%s path=%s", request_id, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "message": "서버 내부 오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
                "request_id": request_id,
            }
        },
    )


@app.get("/api/health")
async def health_check():
    return {"status": "ok"}


app.include_router(notion_router)
app.include_router(linear_router)
app.include_router(spotify_router)
app.include_router(google_router)
app.include_router(telegram_router)
