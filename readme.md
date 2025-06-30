CPBL 特定球員數據追蹤後端專案
本專案是一個 Python 後端應用程式，旨在自動從中華職棒大聯盟 (CPBL) 官網爬取特定球隊與球員的比賽數據。它能獲取球季累積數據、每日比賽結果，以及精細至逐打席的完整紀錄。所有數據均儲存於 SQLite 資料庫，並透過 FastAPI 提供 RESTful API 供前端或其他服務調用。專案內建使用 APScheduler 實現全自動排程，能夠根據賽程在比賽日自動觸發爬蟲。

主要功能
全自動排程：應用程式啟動時，會自動讀取資料庫中的賽程，為未來的比賽設定排程任務，在比賽結束後約 3.5 小時自動抓取當日數據。

精細化數據抓取：不僅抓取比賽總覽和球員單場總結，更能透過瀏覽器自動化，深入文字轉播頁面，抓取目標球員的逐打席詳細記錄，包含對戰投手、好壞球序列、以及打擊前的出局數與壘包狀態。

目標鎖定與設定檔驅動：所有目標（球隊、球員）與爬蟲參數皆由中央設定檔 app/config.py 控制，方便使用者客製化，無需修改主程式碼。

持久化儲存：使用 SQLite 資料庫，並設計了包含賽程、比賽結果、球員單場總結、逐打席記錄、球員球季統計等多個正規化表格，結構清晰。

RESTful API 服務：透過 FastAPI 提供 API 接口，不僅能查詢比賽數據，還能手動觸發賽程更新、單日/多日數據爬取等背景任務。

技術棧
語言: Python 3.8+

Web API 框架: FastAPI

非同步網頁伺服器: Uvicorn

瀏覽器自動化 (處理動態內容): Playwright

HTML/XML 解析: Beautiful Soup 4 (bs4)

排程任務: APScheduler

資料庫: SQLite (使用內建 sqlite3 模組)

數據模型: Pydantic

安裝與設定流程
請遵循以下步驟來完整設定並啟動專案。

1. 克隆 (Clone) 專案庫
   git clone <您的專案庫 URL>
   cd <專案資料夾名稱>

2. 建立並啟動 Python 虛擬環境

# 建立虛擬環境

python -m venv venv

Windows (PowerShell):

.\venv\Scripts\Activate.ps1

macOS / Linux:

source venv/bin/activate

啟動後，您的命令提示字元前應出現 (venv)。

3. 安裝依賴套件
   專案所需的所有 Python 套件都記錄在 requirements.txt 中。

pip install -r requirements.txt

4. 安裝 Playwright 瀏覽器驅動
   Playwright 需要對應的瀏覽器驅動程式來執行自動化操作。

playwright install

(此指令會安裝 Chromium, Firefox, and WebKit。若您僅需特定瀏覽器，可執行 playwright install chromium)

5. 設定追蹤目標
   這是最重要的客製化步驟。請打開設定檔 app/config.py，並修改以下變數：

# app/config.py

# --- 目標設定 ---

TARGET_TEAM_NAME = "台鋼雄鷹"
TARGET_PLAYER_NAMES = ["王柏融", "魔鷹", "吳念庭"]

TARGET_TEAM_NAME：您想追蹤的球隊完整名稱。

TARGET_PLAYER_NAMES：一個包含多位球員姓名的 Python 列表。

啟動與使用指南
專案的運作分為三個主要階段：初始化 -> 啟動服務 -> 更新賽程。

步驟一：初始化資料庫
首次執行專案前，需要建立資料庫檔案及所有表格結構。

python app/db.py

此指令會讀取 app/db.py 中的 CREATE TABLE 敘述，並在 app/data/ 目錄下產生 cpbl_stats.db 檔案。

步驟二：啟動 FastAPI 應用程式
在專案根目錄下執行以下指令，啟動後端服務：

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

--reload 參數會讓伺服器在程式碼變更時自動重啟，方便開發。

步驟三：首次更新賽程 (必要操作)
為了讓排程器知道何時該執行任務，您必須先將本球季的賽程資訊存入資料庫。

應用程式啟動後，請使用 curl 或任何 API 測試工具 (如 Postman)，向以下端點發送一個 POST 請求：

curl -X POST [http://127.0.0.1:8000/api/update_schedule](http://127.0.0.1:8000/api/update_schedule)

此請求會觸發一個背景任務，執行 app/core/schedule_scraper.py，爬取官網從 3 月到 10 月的完整賽程，並存入資料庫。

完成後，它會自動重設排程器，讀取新存入的賽程並設定好所有未來的爬蟲任務。

注意：此操作每年球季初執行一次即可，或在賽程有重大變動時再次執行。

API 端點說明
應用程式提供以下 API 端點供您互動：

1. 取得指定日期的比賽結果
   Endpoint: GET /api/games/{game_date}

說明: 查詢並回傳指定日期的所有比賽基本資料。

範例:

curl [http://127.0.0.1:8000/api/games/2025-06-30](http://127.0.0.1:8000/api/games/2025-06-30)

2. 手動觸發賽程更新
   Endpoint: POST /api/update_schedule

說明: 如上所述，此為初始化或更新整個球季賽程的核心工具。觸發後會自動重設排程器。

範例:

curl -X POST [http://127.0.0.1:8000/api/update_schedule](http://127.0.0.1:8000/api/update_schedule)

3. 手動觸發數據爬蟲
   Endpoint: POST /api/run_scraper

說明: 用於手動補跑或測試特定時間範圍的數據爬取，可取代自動排程。

參數:

mode (必要): daily, monthly, yearly

date (可選):

當 mode=daily 時，格式為 "YYYY-MM-DD"。

當 mode=monthly 時，格式為 "YYYY-MM"。

當 mode=yearly 時，格式為 "YYYY"。

範例:

補跑昨天的數據:

curl -X POST "[http://127.0.0.1:8000/api/run_scraper?mode=daily&date=2025-06-29](http://127.0.0.1:8000/api/run_scraper?mode=daily&date=2025-06-29)"

補跑整個五月的數據:

curl -X POST "[http://127.0.0.1:8000/api/run_scraper?mode=monthly&date=2025-05](http://127.0.0.1:8000/api/run_scraper?mode=monthly&date=2025-05)"

日誌 (Logging)
專案運行過程中的所有重要資訊、進度及錯誤都會被記錄下來。日誌檔案位於專案根目錄下的 logs/scraper.log。
