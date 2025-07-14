# Dockerfile

# 1. 使用官方的 Python 3.11 slim 版本作為基礎映像
FROM python:3.11-slim

# 2. 設定工作目錄
WORKDIR /code

# 3. 設定環境變數，讓 Python 的輸出直接顯示，不要緩衝
ENV PYTHONUNBUFFERED=1

# 4. 複製 requirements.txt 並安裝依賴套件
#    這樣做可以利用 Docker 的層快取，如果 requirements.txt 沒變，就不用重新安裝
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. 將整個專案目錄（包含 app/ 子目錄）複製到工作目錄中
COPY . .

# 注意：我們不需要在這裡寫 CMD 或 ENTRYPOINT，
# 因為 fly.toml 的 [processes] 區塊會為我們處理啟動指令。
