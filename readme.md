# CPBL 數據後端專案 (v5.2)

## 專案總覽 (Project Overview)

本專案是一個用於抓取中華職棒（CPBL）官方網站數據的後端服務，旨在提供一個通用、穩健且可擴展的數據平台。它採用容器化技術（Docker）封裝，並已成功部署至 Fly.io 雲端平台。

服務核心功能是自動化爬取比賽賽程、逐場比賽的詳細攻守數據（包含所有球員的逐打席紀錄），以及球員的球季數據歷史。架構上，採用非同步任務佇列（Dramatiq + Redis）來處理耗時的爬蟲任務，並透過一個受 API 金鑰保護的 RESTful API 提供從基本查詢到複雜情境分析的多種數據需求。

## 主要特色 (Features)

- **通用數據抓取**: 自動抓取並儲存賽季中所有球隊、所有球員的逐打席紀錄，而非針對特定目標。
- **歷史數據追蹤**: 記錄球員球季數據的歷史快照，可供分析其表現趨勢。
- **穩健的背景任務**: 使用 Dramatiq 與 Redis，將耗時的爬蟲工作與 API 伺服器分離。
- **容器化開發與部署**: 使用 Docker 與 Docker Compose 建立標準化的開發與生產環境。
- **資料庫版本控制**: 使用 Alembic 管理資料庫結構的遷移。
- **雲端原生架構**: 部署於 Fly.io，將 API (`web`) 與爬蟲 (`worker`) 拆分為獨立服務。
- **豐富的 RESTful API**: 基於 FastAPI，提供多層次的數據查詢與分析能力。
- **服務健康監控**: 內建 `/health` 端點，整合 Fly.io 實現服務自癒與外部告警。
- **結構化日誌與追蹤**: 所有日誌均為 JSON 格式，並為每個請求注入 `request_id`，大幅簡化問題排查。
- **自動化品質控管**: 整合 pre-commit (Ruff, Black) 與 GitHub Actions CI/CD 流程。

## 生產環境架構 (Production Architecture)

本專案在 Fly.io 上的生產環境由以下幾個核心元件組成：

- **Fly App (`cpbl-takao-today-be`)**: 專案的主應用程式容器。
  - **Web Service (`web`)**: 運行 FastAPI 的 Uvicorn 伺服器，負責接收所有 API 請求。
  - **Worker Service (`worker`)**: 運行 Dramatiq Worker，專門執行來自 Redis 佇列的耗時爬蟲任務。
- **Fly PostgreSQL**: 由 Fly.io 管理的獨立 PostgreSQL 資料庫服務。
- **Aiven Redis**: 作為外部第三方服務的 Redis，是 Dramatiq 所需的訊息代理。

```mermaid
graph TD
    subgraph "使用者"
        Client[外部客戶端 / 前端]
    end

    subgraph "Fly.io 雲端平台"
        subgraph "Fly App: cpbl-takao-today-be"
            Web[Web Service / FastAPI]
            Worker[Worker Service / Dramatiq]
        end
        DB[(Fly PostgreSQL)]
    end

    subgraph "第三方服務"
        Broker[(Aiven Redis)]
    end

    subgraph "外部網站"
        CPBL[CPBL 官網]
    end

    Client -- "API 請求 (HTTPS)" --> Web
    Web -- "1. 查詢請求" --> DB
    DB -- "2. 回傳資料" --> Web
    Web -- "3. 回應資料" --> Client

    Web -- "A. 發送背景任務" --> Broker
    Broker -- "B. 任務入隊" --> Worker
    Worker -- "C. 執行爬蟲" --> CPBL
    Worker -- "D. 將結果寫入資料庫" --> DB
```

## 技術棧 (Tech Stack)

| 類別                   | 技術                                    |
| ---------------------- | --------------------------------------- |
| **後端框架**           | FastAPI, Uvicorn                        |
| **資料庫**             | PostgreSQL, SQLAlchemy (ORM), Alembic   |
| **背景任務佇列**       | Dramatiq, Redis (Aiven)                 |
| **網頁爬蟲**           | Playwright, BeautifulSoup4, Requests    |
| **容器化**             | Docker, Docker Compose                  |
| **雲端平台**           | Fly.io                                  |
| **CI/CD 與程式碼品質** | GitHub Actions, pre-commit, Ruff, Black |
| **測試框架**           | pytest, pytest-mock, pytest-playwright  |
| **設定管理**           | pydantic-settings                       |
| **日誌**               | python-json-logger                      |

## 本地開發環境設定 (Local Development Setup)

請遵循以下步驟在你的本地機器上設定並運行此專案。

### 步驟一：克隆專案

```bash
git clone <YOUR_REPOSITORY_URL>
cd <PROJECT_DIRECTORY>
```

### 步驟二：建立環境變數檔案 (`.env`)

在專案的根目錄下，手動建立一個名為 `.env` 的檔案。此檔案用於存放本地開發所需的敏感資訊與設定，且已被 `.gitignore` 排除，不會被提交至版本控制。

複製以下內容至你的 `.env` 檔案中，並修改 `API_KEY` 的值：

```env
# .env

# 在容器環境中，主機名稱應為服務名稱 'db'
# 但為了讓本地工具 (如 psql) 能連線，這裡仍可保留 localhost
DATABASE_URL=postgresql://myuser:mypassword@localhost:5432/mydb

# 在容器環境中，主機名稱應為服務名稱 'redis'
DRAMATIQ_BROKER_URL=redis://localhost:6379/0

# 用於保護 API 端點的密鑰，請更換為一個你自己的安全字串
API_KEY=your_secret_api_key_here
```

### 步驟三：啟動並初始化服務

本專案使用 Docker Compose 管理所有服務。

```bash
# 首次啟動或 Dockerfile/docker-compose.yml 變更後，使用 --build
docker compose up -d --build
```

### 步驟四：初始化資料庫 (首次設定必要)

在首次啟動服務後，你需要使用 Alembic 在資料庫中建立所有必要的資料表。

```bash
# 在 web 容器中執行 alembic upgrade 指令
docker compose run --rm web alembic upgrade head
```

此指令會將資料庫結構更新到最新的版本。

## 使用方式

當所有服務都成功啟動，且資料庫也已初始化後，即可開始使用。

### 首次初始化賽程

使用 `curl` 或任何 API 測試工具，向以下端點發送一個 POST 請求。請記得將 `your_secret_api_key_here` 替換為你在 `.env` 檔案中設定的 `API_KEY`。

```bash
curl -X POST [http://127.0.0.1:8000/api/update_schedule](http://127.0.0.1:8000/api/update_schedule) \
-H "X-API-Key: your_secret_api_key_here"
```

此請求會發送一個任務到背景佇列，Worker 接收到後便會開始爬取整年度的賽程。

## 資料庫遷移 (Database Migrations)

本專案使用 Alembic 來管理資料庫結構的變更。

- **當你修改 `app/models.py` 中的模型後**，你需要產生一個新的遷移腳本：
  ```bash
  # 在 web 容器中自動產生遷移腳本
  docker compose run --rm web alembic revision --autogenerate -m "描述你的變更"
  ```
- **將變更應用到資料庫**:
  ```bash
  # 在 web 容器中執行 upgrade
  docker compose run --rm web alembic upgrade head
  ```

## API 端點 (API Endpoints)

### 1. 取得指定日期的比賽結果

- **Endpoint**: `GET /api/games/{game_date}`
- **說明**: 查詢並回傳指定日期的所有比賽基本資料。
- **範例**:
  ```bash
  curl [http://127.0.0.1:8000/api/games/2025-07-16](http://127.0.0.1:8000/api/games/2025-07-16)
  ```

### 2. 手動觸發賽程更新

- **Endpoint**: `POST /api/update_schedule`
- **說明**: 觸發一個背景任務來爬取本賽季的完整賽程。主要用於首次初始化或賽程有重大變動時。
- **Headers**:
  - `X-API-Key`: 你的 API 金鑰
- **範例**:
  ```bash
  curl -X POST [http://127.0.0.1:8000/api/update_schedule](http://127.0.0.1:8000/api/update_schedule) \
  -H "X-API-Key: your_secret_api_key_here"
  ```

### 3. 手動觸發數據爬蟲

- **Endpoint**: `POST /api/run_scraper`
- **說明**: 用於手動補跑或測試特定時間範圍的數據爬取。
- **Headers**:
  - `X-API-Key`: 你的 API 金鑰
  - `Content-Type`: `application/json`
- **Body (JSON)**:
  - `mode` (str, 必要): `daily`, `monthly`, 或 `yearly`。
  - `date` (str, 可選): 指定日期/月份/年份。格式分別為 `"YYYY-MM-DD"`, `"YYYY-MM"`, `"YYYY"`。
- **範例**:

  - **補跑昨天的數據**:

    ```bash
    curl -X POST [http://127.0.0.1:8000/api/run_scraper](http://127.0.0.1:8000/api/run_scraper) \
    -H "X-API-Key: your_secret_api_key_here" \
    -H "Content-Type: application/json" \
    -d '{"mode": "daily", "date": "2025-07-15"}'
    ```

  - **補跑整個六月的數據**:
    ```bash
    curl -X POST [http://127.0.0.1:8000/api/run_scraper](http://127.0.0.1:8000/api/run_scraper) \
    -H "X-API-Key: your_secret_api_key_here" \
    -H "Content-Type: application/json" \
    -d '{"mode": "monthly", "date": "2025-06"}'
    ```

### 4.批次匯入歷史數據 (bulk_import.py)

`bulk_import.py` 是一個獨立的命令列工具，用於批次抓取指定日期範圍的歷史比賽數據。為了確保操作的穩定性與可控性，整個流程被拆分為兩個可獨立執行的步驟。

---

#### 執行環境

此腳本應在專案的根目錄下，於已啟動本地 Python 虛擬環境的終端機中執行。它會分別讀取 `.env`（本地資料庫）和 `.env.prod`（雲端資料庫）檔案來取得連線設定。

---

#### 步驟一：爬取資料至本地資料庫

此步驟會將指定日期範圍的比賽數據，完整地爬取並儲存到你本地的 PostgreSQL 開發資料庫中。

##### 指令格式:

```bash
python bulk_import.py scrape --start YYYY-MM-DD [--end YYYY-MM-DD]
```

- `--start` (必要): 爬取的起始日期，格式為 `YYYY-MM-DD`。
- `--end` (可選): 爬取的結束日期，格式為 `YYYY-MM-DD`。如果省略，預設為執行指令的當天日期。

##### 範例:

```bash
# 爬取 2024 年 4 月 1 日至 2024 年 4 月 10 日的數據
python bulk_import.py scrape --start 2024-04-01 --end 2024-04-10
```

此過程會逐日爬取，並在每次請求間有 5 秒的延遲，以避免對目標網站造成過大負擔。若中途發生錯誤，腳本會記錄錯誤並繼續執行下一天。

---

#### 步驟二：從本地上傳資料至雲端

在確認本地資料庫的數據完整無誤後，執行此步驟，將本地資料庫中的所有內容同步至雲端生產資料庫。

##### 指令格式:

```bash
python bulk_import.py upload
```

此指令會：

- 連線至 `.env` 指定的本地資料庫（來源）與 `.env.prod` 指定的雲端資料庫（目標）。
- 逐一比對資料表，使用 SQLAlchemy 的 `merge` 方法來同步資料。`merge` 會根據主鍵判斷：
  - 如果雲端資料庫中不存在該筆紀錄，則新增。
  - 如果已存在，則更新。

整個過程是一個完整的資料庫交易，若中途發生任何錯誤，所有變更都會被復原 (rollback)。

##### 範例:

```bash
# 將本地資料庫的所有內容同步至雲端
python bulk_import.py upload
```

## 資料庫遷移 (Database Migrations)

本專案使用 Alembic 來管理資料庫結構的變更。

- **當你修改 `app/models.py` 中的模型後**，你需要產生一個新的遷移腳本：
  ```bash
  # 在 web 容器中自動產生遷移腳本
  docker compose run --rm web alembic revision --autogenerate -m "描述你的變更"
  ```
- **將變更應用到資料庫**:
  ```bash
  # 在 web 容器中執行 upgrade
  docker compose run --rm web alembic upgrade head
  ```

## 程式碼品質與 CI/CD

- **pre-commit**: 本專案使用 `pre-commit` 在每次 `git commit` 時自動執行 Ruff (linter + formatter) 和 Black (formatter)，以確保所有提交的程式碼都符合一致的風格與品質標準。初次設定請運行 `pre-commit install`。
- **GitHub Actions**: 每次推送到 GitHub 時，會觸發 CI 工作流程。此流程會在一個包含 PostgreSQL 和 Redis 服務的乾淨環境中，依序執行程式碼風格檢查、格式化檢查與完整的 `pytest` 測試套件。

## 部署 (Deployment)

本專案透過 `flyctl` CLI 工具部署至 Fly.io。

1.  **設定秘密 (Secrets)**:
    在部署前，必須將生產環境所需的敏感資訊安全地設定為 Fly.io 的 secrets。這些資訊絕不應存放在版本控制中。

    ```bash
    fly secrets set \
      DATABASE_URL="<YOUR_FLY_POSTGRES_URL>" \
      DRAMATIQ_BROKER_URL="<YOUR_AIVEN_REDIS_URL>" \
      API_KEY="<YOUR_PRODUCTION_API_KEY>"
    ```

2.  **部署應用**:
    設定完 secrets 後，在專案根目錄執行以下指令即可觸發部署。
    ```bash
    fly deploy
    ```
    `flyctl` 會讀取 `fly.toml` 檔案，在本機建置 Docker 映像檔，並將其推送到 Fly.io 平台，更新 `web` 與 `worker` 服務。

## 本地日誌查看技巧 (Local Log Viewing)

由於主控台日誌已改為結構化的 JSON 格式，建議搭配使用命令列工具 `jq` 來美化、上色及過濾日誌。

**前置需求**:
請先確保你的系統已安裝 `jq` (例如在 Ubuntu/WSL 中執行 `sudo apt-get install jq`)。

**美化輸出**:

```bash
# 查看 web 服務的美化日誌
docker compose logs web | jq

# 持續追蹤 worker 服務的美化日誌
docker compose logs -f worker | jq
```

**依 request_id 過濾**:
當你需要追蹤單一 API 請求的完整生命週期時，可利用我們新增的 `request_id` 欄位進行過濾。

```bash
# 只顯示特定 request_id 的日誌記錄
docker compose logs web | jq 'select(.request_id == "YOUR_REQUEST_ID_HERE")'
```
