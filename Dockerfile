FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/requirements.txt backend/requirements-vm.txt /app/
RUN pip install -r requirements-vm.txt
COPY backend/app /app/app
COPY backend/tests /app/tests
COPY AGENT_API.md /app/AGENT_API.md
COPY frontend/dist /app/frontend/dist
ENV DATABASE_PATH=/data/reelvault.db THUMBNAILS_FOLDER=/data/thumbnails CACHE_FOLDER=/data/cache \
    FRONTEND_DIST=/app/frontend/dist REELS_FOLDER=/data/local-reels AUTH_REQUIRED=true
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz')"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log"]
