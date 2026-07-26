# ---- Stage 1: build the frontend ----
FROM node:22-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- Stage 2: Python runtime ----
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Dependencies first, for layer caching. README.md is copied because
# pyproject.toml declares it and the project build reads it.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY backend/ ./backend/
COPY main.py ./
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

# Persisted state lives under /app/data — mount a volume there.
# DATA_DIR holds conversations; STATE_DIR holds matters and user accounts.
ENV DATA_DIR=/app/data/conversations \
    STATE_DIR=/app/data \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

EXPOSE 8001

# Bind to $PORT when the platform injects one, else 8001. Exec form via sh so
# the variable is expanded at run time rather than baked in at build time.
CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8001}"]
