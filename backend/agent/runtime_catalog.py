from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass


@dataclass
class CatalogEntry:
    user_id: str
    catalog_id: str
    payload_hash: str
    payload: dict
    created_at: float
    expires_at: float


_CATALOG_STORE: dict[str, CatalogEntry] = {}
_USER_CATALOG_INDEX: dict[str, set[str]] = {}
_DEFAULT_TTL_SEC = 1800.0


def _stable_payload_hash(payload: dict) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _new_catalog_id(user_id: str, payload_hash: str) -> str:
    basis = f"{user_id}:{payload_hash}"
    digest = hashlib.sha256(basis.encode("utf-8")).hexdigest()[:20]
    return f"catalog_{digest}"


def _cleanup_expired(now_ts: float | None = None) -> None:
    now_value = now_ts if now_ts is not None else time.time()
    expired_ids = [catalog_id for catalog_id, entry in _CATALOG_STORE.items() if entry.expires_at <= now_value]
    for catalog_id in expired_ids:
        entry = _CATALOG_STORE.pop(catalog_id, None)
        if entry is None:
            continue
        user_ids = _USER_CATALOG_INDEX.get(entry.user_id)
        if user_ids is None:
            continue
        user_ids.discard(catalog_id)
        if not user_ids:
            _USER_CATALOG_INDEX.pop(entry.user_id, None)


def get_or_create_catalog_id(
    *,
    user_id: str,
    catalog_payload: dict,
    ttl_sec: float = _DEFAULT_TTL_SEC,
) -> tuple[str, bool]:
    now_ts = time.time()
    _cleanup_expired(now_ts)
    normalized_user_id = str(user_id or "").strip()
    if not normalized_user_id:
        raise ValueError("user_id_required")
    if not isinstance(catalog_payload, dict):
        raise ValueError("catalog_payload_must_be_object")

    payload_hash = _stable_payload_hash(catalog_payload)
    catalog_id = _new_catalog_id(normalized_user_id, payload_hash)
    existing = _CATALOG_STORE.get(catalog_id)
    if existing is not None and existing.expires_at > now_ts:
        existing.expires_at = now_ts + max(60.0, float(ttl_sec))
        return catalog_id, False

    entry = CatalogEntry(
        user_id=normalized_user_id,
        catalog_id=catalog_id,
        payload_hash=payload_hash,
        payload=catalog_payload,
        created_at=now_ts,
        expires_at=now_ts + max(60.0, float(ttl_sec)),
    )
    _CATALOG_STORE[catalog_id] = entry
    _USER_CATALOG_INDEX.setdefault(normalized_user_id, set()).add(catalog_id)
    return catalog_id, True


def get_catalog(catalog_id: str) -> dict | None:
    _cleanup_expired()
    key = str(catalog_id or "").strip()
    if not key:
        return None
    entry = _CATALOG_STORE.get(key)
    if entry is None:
        return None
    if entry.expires_at <= time.time():
        _cleanup_expired()
        return None
    return dict(entry.payload)


def invalidate_catalog(user_id: str, reason: str | None = None) -> int:
    _ = reason
    _cleanup_expired()
    normalized_user_id = str(user_id or "").strip()
    if not normalized_user_id:
        return 0
    targets = list(_USER_CATALOG_INDEX.get(normalized_user_id) or [])
    count = 0
    for catalog_id in targets:
        if _CATALOG_STORE.pop(catalog_id, None) is not None:
            count += 1
    _USER_CATALOG_INDEX.pop(normalized_user_id, None)
    return count
