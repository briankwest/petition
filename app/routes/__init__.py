"""Shared template environment + render helper."""
from __future__ import annotations
from datetime import date, datetime
import os
import re
from fastapi import Request
from fastapi.templating import Jinja2Templates
from toolkit import ROOT, config as cfg
from ..auth import csrf_token
from ..settings import DEFAULTS

templates = Jinja2Templates(directory=str(ROOT / "app" / "templates"))


def fmt_date(v, placeholder="—"):
    if not v:
        return placeholder
    if isinstance(v, str):
        try:
            v = date.fromisoformat(v)
        except ValueError:
            return v
    if isinstance(v, datetime):
        return v.strftime("%b %-d, %Y %-I:%M %p")
    return v.strftime("%B %-d, %Y")


def fmt_int(v, placeholder="—"):
    return f"{int(v):,}" if v is not None else placeholder


def fmt_pct(v, placeholder="—"):
    return f"{v * 100:.0f}%" if v is not None else placeholder


def tel(v):
    return "+1" + re.sub(r"\D", "", v or "")[-10:] if v else ""


def fmt_time(v):
    return v.strftime("%-I:%M %p") if v else ""


templates.env.filters.update({"date": fmt_date, "int": fmt_int, "pct": fmt_pct, "tel": tel, "time": fmt_time})


def render(request: Request, name: str, status_code: int = 200, **ctx):
    petition = getattr(request.app.state, "petition", None)
    if petition is None:
        petition = cfg.load()
        request.app.state.petition = petition
    base = {
        "petition": petition,
        "csrf": csrf_token(request),
        "user": getattr(request.state, "user", None),
        "path": request.url.path,
        "msg": request.query_params.get("msg"),
        "err": request.query_params.get("err"),
        "today": date.today(),
        "ga_id": os.environ.get("GA_MEASUREMENT_ID", "G-3ECCW6ESQR"),
    }
    s = ctx.get("s")
    base["site_title"] = (s.raw("site_title") if s is not None else None) or DEFAULTS["site_title"]
    base["site_eyebrow"] = (s.raw("site_eyebrow") if s is not None else None) or f"{petition.county} County, {petition.state}"
    base.update(ctx)
    return templates.TemplateResponse(request=request, name=name, context=base, status_code=status_code)
