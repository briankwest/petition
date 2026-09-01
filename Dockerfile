# petition.mcalester.net — FastAPI app for Dokku (Dockerfile deploy).
# The image also renders the legal-size documents and the wall map at build time (WeasyPrint +
# Liberation fonts) into /srv/dist so the admin "Documents" page can preview exactly what this
# deploy would print. Config for the documents is config/petition.yaml (in git), not the database.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 MPLBACKEND=Agg XDG_CACHE_HOME=/tmp/cache
RUN apt-get update && apt-get install -y --no-install-recommends \
      libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libharfbuzz-subset0 libffi8 shared-mime-info poppler-utils \
      fonts-liberation fonts-dejavu-core fontconfig \
    && fc-cache -f && rm -rf /var/lib/apt/lists/*
WORKDIR /srv
COPY requirements-app.txt ./
RUN pip install --no-cache-dir -r requirements-app.txt
COPY pyproject.toml ./
COPY toolkit/ ./toolkit/
COPY app/ ./app/
COPY config/ ./config/
COPY data/ ./data/
COPY reference/ ./reference/
COPY templates/ ./templates/
COPY measure/ ./measure/
ARG GIT_SHA=
ENV GIT_SHA=$GIT_SHA
RUN python -m toolkit.docs.build --out dist/docs && python -m toolkit.geo.build_map --out dist/map \
    && rm -rf dist/map/data dist/map/map.js dist/map/map.css dist/map/index.html
RUN mkdir -p /srv/output && useradd -r -u 10001 petition && chown -R petition:petition /srv
USER petition
EXPOSE 5000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-5000} --proxy-headers --forwarded-allow-ips='*'"]
