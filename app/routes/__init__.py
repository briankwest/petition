"""Shared template environment + render helper."""
from __future__ import annotations
from datetime import date, datetime
import copy
import os
import re
from fastapi import Request
from fastapi.templating import Jinja2Templates
from toolkit import ROOT, config as cfg
from ..auth import csrf_token
from ..settings import DEFAULTS

templates = Jinja2Templates(directory=str(ROOT / "app" / "templates"))
# cache-busting query for /static links: newest mtime under app/static at process start
try:
    ASSET_V = str(int(max(os.path.getmtime(p) for p in __import__("glob").glob(str(ROOT / "app" / "static" / "**" / "*"), recursive=True) if os.path.isfile(p))))
except ValueError:
    ASSET_V = "1"


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
from toolkit import statutes as _statutes
from markupsafe import Markup, escape as _escape
templates.env.globals["cite_url"] = lambda sec: _statutes.html_url(sec) or _statutes.cite_url(sec)
_CITE_RE = re.compile(r"(\d{2}) O\.S\. § ?(\d+(?:\.\d+)?)((?:\([A-Za-z0-9]{1,3}\))*)")
_KNOWN = set(_statutes.available())


def linkcites(text) -> Markup:
    """Escape plain text and turn known statute citations into links (help text, flash messages)."""
    if text is None:
        return Markup("")
    s = str(_escape(text))
    def sub(m):
        sec = f"{m.group(1)}-{m.group(2)}"
        if sec not in _KNOWN:
            return m.group(0)
        url = _statutes.html_url(sec) or _statutes.cite_url(sec)
        return f'<a class="cite" href="{url}" rel="noopener" target="_blank">{m.group(0)}</a>'
    return Markup(_CITE_RE.sub(sub, s))


templates.env.filters["linkcites"] = linkcites


def addr(v) -> Markup:
    """Street on one line; 'City, ST ZIP' kept together on the next."""
    if not v:
        return Markup("")
    parts = [p.strip() for p in str(v).split(",") if p.strip()]
    if len(parts) >= 3:
        head, tail = ", ".join(parts[:-2]), ", ".join(parts[-2:])
        return Markup(f'{_escape(head)},<br><span class="nowrap">{_escape(tail)}</span>')
    return Markup(f'<span class="nowrap">{_escape(str(v))}</span>') if len(parts) == 1 else _escape(str(v))


templates.env.filters["addr"] = addr


def render(request: Request, name: str, status_code: int = 200, **ctx):
    petition = getattr(request.app.state, "petition", None)
    if petition is None:
        petition = cfg.load()
        request.app.state.petition = petition
    s = ctx.get("s")
    if s is not None and "petition" not in ctx:
        # Overlay the admin-entered values (gist, abatement, dates, districts, captain, voter count) on a
        # copy of the YAML seed, so the public site shows what /admin/petition shows. The copy matters:
        # from_db mutates its base, and app.state.petition is shared across requests.
        from ..petition import from_db
        petition = from_db(s.db, copy.deepcopy(petition))
    base = {
        "petition": petition,
        "csrf": csrf_token(request),
        "user": getattr(request.state, "user", None),
        "path": request.url.path,
        "msg": request.query_params.get("msg"),
        "err": request.query_params.get("err"),
        "today": date.today(),
        "ga_id": os.environ.get("GA_MEASUREMENT_ID", "G-3ECCW6ESQR"),
        "asset_v": ASSET_V,
    }
    base["site_title"] = (s.raw("site_title") if s is not None else None) or DEFAULTS["site_title"]
    base["site_eyebrow"] = (s.raw("site_eyebrow") if s is not None else None) or f"{petition.county} County, {petition.state}"
    base["site_description"] = (s.raw("site_description") if s is not None else None) or DEFAULTS["site_description"]
    base["canonical_host"] = os.environ.get("CANONICAL_HOST") or petition.canonical_host
    base.update(ctx)
    return templates.TemplateResponse(request=request, name=name, context=base, status_code=status_code)
