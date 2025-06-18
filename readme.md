# CPBL 特定球員數據追蹤後端專案

本專案是一個 Python 後端應用程式，用於從中華職棒大聯盟 (CPBL) 官網爬取特定球隊的特定球員每日比賽數據、逐打席記錄等，並將數據儲存於 SQLite 資料庫，同時透過 FastAPI 提供 API 供前端或其他服務調用。專案內建使用 APScheduler 定時更新數據。

## 主要功能

- **定時爬取**：每日自動從 CPBL 官網抓取最新數據。
- **目標鎖定**：專注於使用者設定的特定球隊及球員，提高效率。
- **數據儲存**：使用 SQLite 儲存結構化的比賽結果、球員單場總結及逐打席詳細記錄。
- **API 服務**：透過 FastAPI 提供 RESTful API 接口，方便查詢所需數據。
- **詳細記錄**：能夠記錄球員的逐打席描述、對戰投手及好壞球過程。

## 技術棧

- **語言**: Python 3.8+
- **HTTP 請求**: Requests
- **HTML/XML 解析**: Beautiful Soup 4 (bs4), lxml
- **瀏覽器自動化 (處理動態內容)**: Playwright
- **Web API 框架**: FastAPI
- **資料庫**: SQLite
- **排程任務**: APScheduler
- **伺服器**: Uvicorn

## 環境需求

- Python 3.8 或更高版本
- pip (Python 套件安裝器)
- Git (版本控制)

## 安裝與設定步驟

1.  **克隆 (Clone) 專案庫：**

    ```bash
    git clone <您的專案庫URL>
    cd <專案資料夾名稱>
    ```

2.  **建立並啟動 Python 虛擬環境：**

    ```bash
    python -m venv venv
    ```

    - Windows (cmd.exe):
      ```bash
      venv\Scripts\activate
      ```
    - Windows (PowerShell):
      ```bash
      venv\Scripts\Activate.ps1
      ```
    - macOS / Linux:
      `bash
    source venv/bin/activate
    `
      啟動後，命令提示字元前應出現 `(venv)`。

3.  **安裝依賴套件：**

    ```bash
    pip install -r requirements.txt
    ```

    _(請確保您已在專案根目錄執行 `pip freeze > requirements.txt` 來產生此檔案)_

4.  **安裝 Playwright 瀏覽器驅動：**

    ```bash
    playwright install
    ```

    (這會安裝 Chromium, Firefox, WebKit 的驅動。如果只需要特定瀏覽器，例如 `playwright install chromium`)

5.  **設定目標球隊與球員：**
    打開 `app/scraper.py` 檔案，修改檔案頂部的 `TARGET_TEAM_NAME` 和 `TARGET_PLAYER_NAMES` 常數：

    ```python
    # app/scraper.py
    # --- 設定目標球隊與球員 ---
    TARGET_TEAM_NAME = "您想追蹤的球隊名稱"  # 例如："中信兄弟"
    TARGET_PLAYER_NAMES = ["球員A", "球員B", "球員C"] # 您想追蹤的球員姓名列表
    ```

6.  **初始化資料庫：**
    執行以下命令來建立 SQLite 資料庫檔案 (`app/data/cpbl_stats.db`) 及所需的表格結構：

    ```bash
    python app/db.py
    ```

    這會在 `app/data/` 目錄下產生資料庫檔案。

7.  **重要 - 配置爬蟲解析邏輯：**
    打開 `app/scraper.py` 檔案。找到以下函式（或類似的函式）：
    - `get_all_games_for_date()`: **您必須實現此函式**，使其能夠正確抓取指定日期的所有比賽基本資訊，特別是每場比賽的 Box Score 頁面 URL。
    - `parse_and_store_target_players_stats_from_box()`: **這是最關鍵的部分**。您需要根據 CPBL 官網 Box Score 頁面的**實際 HTML 結構**，修改此函式內部使用 `BeautifulSoup` 進行數據提取的選擇器 (例如 `soup.find_all(...)` 中的 class 名稱、id 等)。所有標有 `# --- 佔位符 ---` 或 `# --- 根據實際 HTML 修改 ---` 的註解處都需要您仔細檢查並編寫。

## 啟動應用程式

在專案根目錄（`app` 資料夾的上一層）執行以下命令以啟動 FastAPI 開發伺服器：

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
