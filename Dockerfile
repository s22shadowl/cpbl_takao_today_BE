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
    playwright install --with-deps && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# 6. 將整個專案目錄複製到工作目錄中
COPY . .

# --- 核心修正 ---
# 7. 將我們自訂的啟動腳本複製進來，並賦予它執行權限
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

# 8. 將此腳本設定為容器的進入點
ENTRYPOINT ["./entrypoint.sh"]
