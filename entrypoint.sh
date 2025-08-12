#!/bin/bash
# 關閉 Bash 的作業控制，這在某些容器環境中是必要的
set -m

# 在背景啟動 Xvfb，並將其監聽的虛擬螢幕設定為 :99
# -screen 0 1280x720x24: 設定虛擬螢幕的解析度和色彩深度
# &：將命令放到背景執行
Xvfb :99 -screen 0 1280x720x24 &

# 將 DISPLAY 環境變數設定為我們剛剛建立的虛擬螢幕
export DISPLAY=:99

# 使用 exec "$@" 來執行傳遞給此腳本的任何命令
# (例如 "uvicorn app.main:app..." 或 "dramatiq app.workers")
# exec 會讓主應用程式取代 shell，能正確地接收和處理來自 Fly.io 的關閉信號
exec "$@"
