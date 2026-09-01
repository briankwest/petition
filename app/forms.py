"""Form parsing helpers (server-rendered HTML forms)."""
from __future__ import annotations
from datetime import date, time
from fastapi import Request
from starlette.datastructures import FormData
from .auth import check_csrf


async def parse(request: Request, csrf: bool = True) -> FormData:
    form = await request.form()
    if csrf:
        check_csrf(request, form)
    return form


def s(form, key: str, default: str | None = None) -> str | None:
    v = form.get(key)
    if v is None:
        return default
    v = str(v).strip()
    return v if v != "" else default


def i(form, key: str, default: int | None = None) -> int | None:
    v = s(form, key)
    if v is None:
        return default
    try:
        return int(float(v))
    except ValueError:
        return default


def f(form, key: str, default: float | None = None) -> float | None:
    v = s(form, key)
    if v is None:
        return default
    try:
        return float(v)
    except ValueError:
        return default


def d(form, key: str) -> date | None:
    v = s(form, key)
    if not v:
        return None
    try:
        return date.fromisoformat(v)
    except ValueError:
        return None


def t(form, key: str) -> time | None:
    v = s(form, key)
    if not v:
        return None
    try:
        return time.fromisoformat(v)
    except ValueError:
        return None


def b(form, key: str) -> bool:
    v = form.get(key)
    return str(v).lower() in ("1", "true", "on", "yes") if v is not None else False


def lst(form, key: str) -> list[str]:
    return [str(x).strip() for x in form.getlist(key) if str(x).strip()]
