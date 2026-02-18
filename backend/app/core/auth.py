import httpx
from fastapi import HTTPException, Request

from app.core.config import get_settings


async def get_authenticated_user_id(request: Request) -> str:
    authorization = request.headers.get("authorization", "")
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="인증 토큰이 필요합니다.")

    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="유효한 인증 토큰이 필요합니다.")

    settings = get_settings()
    auth_url = f"{settings.supabase_url}/auth/v1/user"

    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(
            auth_url,
            headers={
                "Authorization": f"Bearer {token}",
                "apikey": settings.supabase_service_role_key,
            },
        )

    if response.status_code >= 400:
        raise HTTPException(status_code=401, detail="인증 토큰 검증에 실패했습니다.")

    payload = response.json()
    user_id = payload.get("id")
    if not user_id:
        raise HTTPException(status_code=401, detail="인증 사용자 정보를 찾을 수 없습니다.")

    return user_id
