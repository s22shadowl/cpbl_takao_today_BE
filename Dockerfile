# 1. 使用官方的 Python 3.11 slim 版本作為基礎映像
FROM python:3.11-slim

# 2. 設定工作目錄
WORKDIR /code

# 3. 設定環境變數
ENV PYTHONUNBUFFERED=1

# 4. 先將 requirements.txt 複製到工作目錄中
COPY requirements.txt .

# 5. 安裝系統依賴和 Python 依賴
RUN apt-get update && \
    apt-get install -y xvfb && \
    pip install --no-cache-dir -r requirements.txt && \
    # 只安裝 Chromium 瀏覽器核心，以大幅縮小映像檔體積。
    playwright install chromium --with-deps && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# 6. 將整個專案目錄複製到工作目錄中
COPY . .

# 注意：ENTRYPOINT 和 CMD 將在 docker-compose.yml 中定義
