# syntax=docker/dockerfile:1
# Three images from one file; pick one with --target:
#   web     the website (built React files) served by nginx, with /api/ passed on to the API
#   api     the Flask API, run by gunicorn
#   worker  the OCR worker: Python + the Claude Code CLI

FROM node:24-trixie-slim AS node

# ---------- website: build ----------
FROM node AS website-build
WORKDIR /website
COPY website/package.json website/package-lock.json ./
RUN npm ci
COPY website/ ./
RUN npm run build

# ---------- web ----------
FROM nginxinc/nginx-unprivileged:1.28-alpine AS web
# Where /api/ goes. The nginx image writes it into the template when the container starts.
ENV API_UPSTREAM=http://api:5000 \
    NGINX_ENVSUBST_FILTER=^API_UPSTREAM$
COPY docker/nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY docker/nginx/security-headers.conf /etc/nginx/snippets/security-headers.conf
COPY --from=website-build /website/dist /usr/share/nginx/html
EXPOSE 8080

# ---------- Python base of the API and the worker ----------
FROM python:3.11-slim-trixie AS python-base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore
WORKDIR /app
RUN useradd --create-home --uid 10001 app
COPY requirements.txt .
RUN pip install -r requirements.txt
# The code is owned by root: the app can read it, not change it.
COPY backend/ backend/
# The local file storage (used only when GCS_BUCKET is empty): the one folder the app writes to.
RUN mkdir -p backend/storage && chown app:app backend/storage

# ---------- api ----------
FROM python-base AS api
USER app
EXPOSE 5000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s \
    CMD python -c "import socket; socket.create_connection(('127.0.0.1', 5000), 2)"
# 2 processes x 8 threads: requests mostly wait on the database, the storage and file downloads.
CMD ["gunicorn", "backend.app:create_app()", \
     "--bind", "0.0.0.0:5000", \
     "--worker-class", "gthread", "--workers", "2", "--threads", "8", \
     "--timeout", "120", "--graceful-timeout", "30", \
     "--worker-tmp-dir", "/dev/shm", \
     "--access-logfile", "-"]

# ---------- worker ----------
FROM python-base AS worker
ARG CLAUDE_CODE_VERSION=2.1.299
# Node from the official image (same Debian), then the Claude Code CLI at a fixed version.
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/npm
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
 && npm install -g @anthropic-ai/claude-code@${CLAUDE_CODE_VERSION} \
 && npm cache clean --force \
 && claude --version \
 && apt-get update && apt-get install -y --no-install-recommends tini \
 && rm -rf /var/lib/apt/lists/*
# No auto-update (the version is fixed above), no telemetry or error reports from the CLI.
ENV DISABLE_AUTOUPDATER=1 \
    CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1
USER app
# The worker gives its file back to the queue on Ctrl+C (KeyboardInterrupt): stop it with SIGINT, not SIGTERM.
STOPSIGNAL SIGINT
# tini passes the stop signal on and cleans up the CLI's child processes.
ENTRYPOINT ["tini", "--"]
CMD ["python", "-m", "backend.jobs.bbm_ocr.worker"]
