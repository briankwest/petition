# petition.mcalester.net — FastAPI app for Dokku (Dockerfile deploy). No WeasyPrint here:
# documents are built offline with `make docs`; the site serves data, admin and the map.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /srv
COPY requirements-app.txt ./
RUN pip install --no-cache-dir -r requirements-app.txt
COPY pyproject.toml ./
COPY toolkit/ ./toolkit/
COPY app/ ./app/
COPY config/ ./config/
COPY data/ ./data/
COPY reference/ ./reference/
RUN mkdir -p /srv/output && useradd -r -u 10001 petition && chown -R petition:petition /srv
USER petition
EXPOSE 5000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-5000} --proxy-headers --forwarded-allow-ips='*'"]
