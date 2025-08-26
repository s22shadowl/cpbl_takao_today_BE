# Stage 1: base - 安裝所有 Python 依賴
# 使用 bullseye (Debian 11) 版本，這是一個穩定且受 Playwright 支援的系統
FROM python:3.11-slim-bullseye AS base
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=true

WORKDIR /code
RUN pip install poetry
COPY pyproject.toml poetry.lock ./
RUN poetry install --no-root

# Stage 2: playwright_base - 在 base 基礎上安裝 Playwright 瀏覽器
FROM base AS playwright_base
# [修正] 將虛擬環境的路徑加入 PATH，才能找到 playwright 指令
ENV PATH="/code/.venv/bin:$PATH"
RUN playwright install --with-deps chromium

# Stage 3: web - 生產環境用的 web image
FROM python:3.11-slim-bullseye AS web
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
WORKDIR /code
COPY --from=base /code/.venv ./.venv
ENV PATH="/code/.venv/bin:$PATH"
COPY . .

# Stage 4: worker - 生產環境用的 worker image
FROM python:3.11-slim-bullseye AS worker
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
WORKDIR /code
COPY --from=playwright_base /code/.venv ./.venv
COPY --from=playwright_base /root/.cache/ms-playwright /root/.cache/ms-playwright
ENV PATH="/code/.venv/bin:$PATH"
COPY . .
