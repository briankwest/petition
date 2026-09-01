"""Sessions (signed cookie), password hashing (stdlib scrypt), CSRF, login dependencies."""
from __future__ import annotations
import hashlib, hmac, os, secrets
from typing import Any
from fastapi import Request, Depends, HTTPException
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from sqlalchemy.orm import Session
from sqlalchemy import select
from .db import get_db
from .models import User

COOKIE = "petition_session"
MAX_AGE = 60 * 60 * 12  # 12 hours


def secret_key() -> str:
    key = os.environ.get("SECRET_KEY")
    if not key:
        # Dev-only fallback; DEPLOY.md requires SECRET_KEY in production.
        key = os.environ.setdefault("SECRET_KEY", secrets.token_hex(32))
    return key


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(secret_key(), salt="petition-session")


def read_session(request: Request) -> dict[str, Any]:
    if getattr(request.state, "session", None) is not None:
        return request.state.session
    raw = request.cookies.get(COOKIE)
    data: dict[str, Any] = {}
    if raw:
        try:
            data = _serializer().loads(raw, max_age=MAX_AGE) or {}
        except (BadSignature, SignatureExpired):
            data = {}
    if "csrf" not in data:
        data["csrf"] = secrets.token_urlsafe(24)
        data["_dirty"] = True
    request.state.session = data
    return data


def is_https(request: Request) -> bool:
    return request.url.scheme == "https" or request.headers.get("x-forwarded-proto", "").lower() == "https"


def write_session(request: Request, response) -> None:
    data = getattr(request.state, "session", None)
    if data is None:
        return
    payload = {k: v for k, v in data.items() if not k.startswith("_")}
    response.set_cookie(COOKIE, _serializer().dumps(payload), max_age=MAX_AGE, httponly=True,
                        samesite="lax", secure=is_https(request), path="/")


def clear_session(request: Request, response) -> None:
    request.state.session = {"csrf": secrets.token_urlsafe(24), "_dirty": True}
    response.delete_cookie(COOKIE, path="/")


# ---- passwords ----
def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    h = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${h.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, salt_hex, h_hex = stored.split("$")
        if algo != "scrypt":
            return False
        h = hashlib.scrypt(password.encode("utf-8"), salt=bytes.fromhex(salt_hex), n=2 ** 14, r=8, p=1, dklen=32)
        return hmac.compare_digest(h.hex(), h_hex)
    except Exception:
        return False


# ---- dependencies ----
def current_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    sess = read_session(request)
    uid = sess.get("uid")
    if not uid:
        return None
    user = db.get(User, int(uid))
    if user is None or not user.active:
        return None
    request.state.user = user
    return user


def require_user(request: Request, user: User | None = Depends(current_user)) -> User:
    if user is None:
        nxt = request.url.path + (f"?{request.url.query}" if request.url.query else "")
        raise HTTPException(status_code=303, headers={"Location": f"/admin/login?next={nxt}"})
    return user


def require_admin(user: User = Depends(require_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    return user


def csrf_token(request: Request) -> str:
    return read_session(request)["csrf"]


def check_csrf(request: Request, form) -> None:
    token = form.get("csrf") if hasattr(form, "get") else None
    if not token or not hmac.compare_digest(str(token), read_session(request)["csrf"]):
        raise HTTPException(status_code=400, detail="Invalid or missing CSRF token — reload the page and try again.")
