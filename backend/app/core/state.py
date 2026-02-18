import base64
import hashlib
import hmac
import time


def _sign(payload: str, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def build_state(user_id: str, secret: str, ttl_seconds: int = 600) -> str:
    expires_at = int(time.time()) + ttl_seconds
    payload = f"{user_id}:{expires_at}"
    sig = _sign(payload, secret)
    blob = f"{payload}:{sig}"
    return base64.urlsafe_b64encode(blob.encode("utf-8")).decode("utf-8")


def verify_state(state: str, secret: str) -> str | None:
    try:
        decoded = base64.urlsafe_b64decode(state.encode("utf-8")).decode("utf-8")
        user_id, expires_at, sig = decoded.split(":", 2)
    except Exception:
        return None

    payload = f"{user_id}:{expires_at}"
    expected = _sign(payload, secret)

    if not hmac.compare_digest(sig, expected):
        return None

    if int(expires_at) < int(time.time()):
        return None

    return user_id
