"""petition.mcalester.net — FastAPI app factory, host canonicalization, static mounts."""
from __future__ import annotations
import os
import mimetypes
mimetypes.add_type("application/geo+json", ".geojson")
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import sessionmaker
from toolkit import ROOT, config as cfg
from . import db as dbmod
from .auth import write_session

STATIC_DIR = ROOT / "app" / "static"
PRECINCT_DIR = ROOT / "data" / "precincts"


def _canonical_host() -> str:
    env = os.environ.get("CANONICAL_HOST", "").strip()
    if env:
        return env.lower()
    try:
        return cfg.load().canonical_host.lower()
    except Exception:
        return "petition.mcalester.net"


def _allowed_hosts(canonical: str) -> set[str]:
    hosts = {canonical, "localhost", "127.0.0.1", "testserver"}
    extra = os.environ.get("EXTRA_ALLOWED_HOSTS", "")
    hosts.update(h.strip().lower() for h in extra.split(",") if h.strip())
    return hosts


def create_app(engine=None) -> FastAPI:
    engine = engine or dbmod.engine

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        dbmod.init_db(engine)
        yield

    app = FastAPI(title="Pittsburg County Referendum Petition", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.engine = engine
    app.state.canonical_host = _canonical_host()
    app.state.allowed_hosts = _allowed_hosts(app.state.canonical_host)

    if engine is not dbmod.engine:
        Local = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

        def _get_db():
            s = Local()
            try:
                yield s
            finally:
                s.close()
        app.dependency_overrides[dbmod.get_db] = _get_db

    @app.middleware("http")
    async def canonical_host_and_headers(request: Request, call_next):
        path = request.url.path
        if path != "/healthz":
            host = (request.headers.get("x-forwarded-host") or request.headers.get("host") or "").split(",")[0]
            host = host.strip().lower().split(":")[0]
            canonical = request.app.state.canonical_host
            query = f"?{request.url.query}" if request.url.query else ""
            if host and host not in request.app.state.allowed_hosts:
                return RedirectResponse(url=f"https://{canonical}{path}{query}", status_code=301)
            if (host == canonical and request.headers.get("x-forwarded-proto", "").lower() == "http"
                    and os.environ.get("FORCE_HTTPS", "1") != "0"):
                return RedirectResponse(url=f"https://{canonical}{path}{query}", status_code=301)
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        if request.url.path.startswith("/admin/documents/file/"):
            # built PDFs are embedded in the admin preview iframe (same origin only)
            response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
            response.headers.setdefault("Content-Security-Policy", "frame-ancestors 'self'")
        else:
            response.headers.setdefault("X-Frame-Options", "DENY")
            response.headers.setdefault("Content-Security-Policy", "frame-ancestors 'none'")
        if getattr(request.state, "session", None) is not None and request.state.session.get("_dirty"):
            write_session(request, response)
            request.state.session.pop("_dirty", None)
        return response

    @app.get("/healthz")
    def healthz():
        return JSONResponse({"ok": True, "canonical_host": app.state.canonical_host})

    PRECINCT_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/static/precincts", StaticFiles(directory=str(PRECINCT_DIR)), name="precincts")
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    from .routes import public, api, admin
    app.include_router(public.router)
    app.include_router(api.router)
    app.include_router(admin.router)
    return app


app = create_app()
