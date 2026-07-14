from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from app.config import get_settings


SECRET = "prototype-local-secret"


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def verify_password(password: str, password_hash: str) -> bool:
    return hmac.compare_digest(hash_password(password), password_hash)


def create_access_token(user_id: int, role: str) -> str:
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=get_settings().access_token_ttl_minutes)
    payload = f"{user_id}:{role}:{int(expires_at.timestamp())}:{secrets.token_urlsafe(8)}"
    signature = hmac.new(SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    raw = f"{payload}:{signature}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def parse_access_token(token: str) -> tuple[int, str]:
    try:
        raw = base64.urlsafe_b64decode(token.encode()).decode()
        user_id, role, expires_at, nonce, signature = raw.split(":", 4)
    except Exception as exc:
        raise ValueError("Invalid token") from exc

    payload = f"{user_id}:{role}:{expires_at}:{nonce}"
    expected = hmac.new(SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise ValueError("Invalid token")
    if int(expires_at) < int(datetime.now(timezone.utc).timestamp()):
        raise ValueError("Expired token")
    return int(user_id), role


def create_refresh_token() -> str:
    return secrets.token_urlsafe(48)

