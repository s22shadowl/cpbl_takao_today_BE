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

# Stage 2: playwright_base - 在 base 基礎上安裝 Playwright 瀏覽器與系統依賴
FROM base AS playwright_base
# [修正] 將虛擬環境的路徑加入 PATH，才能找到 playwright 指令
ENV PATH="/code/.venv/bin:$PATH"
# --with-deps 會一併安裝 Xvfb 等必要的系統套件
RUN playwright install --with-deps chromium

# Stage 3: web - 生產環境用的 web image
# 這個 stage 不需要 Playwright，所以直接繼承 base 即可
FROM base AS web
WORKDIR /code
# [優化] 直接從 base stage 複製整個 /code 目錄，包含 .venv
COPY --from=base /code /code
ENV PATH="/code/.venv/bin:$PATH"
COPY . .

# Stage 4: worker - 生產環境用的 worker image
# [修正] 直接繼承 playwright_base，這樣才會包含 Xvfb 等系統依賴
FROM playwright_base AS worker
WORKDIR /code
# [優化] playwright_base 已經包含所有需要的東西，只需複製最新的應用程式碼
COPY . .
