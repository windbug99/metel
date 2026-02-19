from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
from fastapi import HTTPException

from app.core.config import get_settings


def _normalize_private_key(raw_key: str) -> str:
    key = raw_key.strip()
    if "\\n" in key:
        key = key.replace("\\n", "\n")
    return key


def generate_apple_music_developer_token() -> str:
    settings = get_settings()
    team_id = (settings.apple_music_team_id or "").strip()
    key_id = (settings.apple_music_key_id or "").strip()
    private_key = _normalize_private_key(settings.apple_music_private_key or "")
    if not team_id or not key_id or not private_key:
        raise HTTPException(status_code=500, detail="Apple Music 개발자 토큰 설정이 누락되었습니다.")

    now = datetime.now(timezone.utc)
    payload = {
        "iss": team_id,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=12)).timestamp()),
    }
    headers = {
        "alg": "ES256",
        "kid": key_id,
        "typ": "JWT",
    }
    encoded = jwt.encode(payload, private_key, algorithm="ES256", headers=headers)
    return str(encoded)


def build_apple_music_headers(music_user_token: str) -> dict[str, str]:
    developer_token = generate_apple_music_developer_token()
    return {
        "Authorization": f"Bearer {developer_token}",
        "Music-User-Token": music_user_token,
    }

