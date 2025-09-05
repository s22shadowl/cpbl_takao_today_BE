# Makefile 用於簡化常見的開發與維護任務。

# --- 設定區 (Configuration) ---
# 預設的爬取日期範圍。可從指令行覆寫。
start ?= $(shell date -I)
end ?= $(shell date -I)

# --- Docker Compose 指令變數 ---
# 這些變數由內部輔助任務使用，會在一個遞迴的 make 程序中被展開。
_WORKER_CMD_XVFB = docker compose run --rm worker sh -c "Xvfb :99 -screen 0 1280x1024x24 & export DISPLAY=:99 && python -m $(script_cmd)"
_WORKER_CMD = docker compose run --rm worker python -m $(script_cmd)


# --- 批次匯入 (Bulk Import) ---
.PHONY: bulk-scrape bulk-scrape-career bulk-update-schedule bulk-upload

# 爬取指定日期範圍的比賽資料。
# 使用範例：
#   make bulk-scrape                                  # 爬取今天的比賽資料
#   make bulk-scrape start=2025-05-01                 # 爬取從 2025-05-01 到今天的資料
#   make bulk-scrape start=2025-03-01 end=2025-04-30  # 爬取 2025-03-01 到 2025-04-30 的資料
bulk-scrape:
	@echo "==> 爬取比賽資料從 [$(start)] 到 [$(end)]..."
	@$(MAKE) -s _run_in_worker_xvfb script_cmd="scripts.bulk_import scrape --start $(start) --end $(end)"

# 爬取所有球員的生涯數據。
bulk-scrape-career:
	@echo "==> 爬取所有球員的生涯數據..."
	@$(MAKE) -s _run_in_worker_xvfb script_cmd="scripts.bulk_import scrape-career"

# 從官網更新最新的賽程資料。
bulk-update-schedule:
	@echo "==> 從官網更新最新賽程..."
	@$(MAKE) -s _run_in_worker script_cmd="scripts.bulk_import update-schedule"

# 將暫存資料庫的資料上傳至生產資料庫。
bulk-upload:
	@echo "==> 從暫存資料庫上傳資料至生產資料庫..."
	@$(MAKE) -s _run_in_worker script_cmd="scripts.bulk_import upload"


# --- 工具與維護 (Tooling & Maintenance) ---
.PHONY: load-test create-canary generate-readme gen-readme reset-db

# 執行 Locust 壓力測試。
# 注意：此指令需要在你的本機環境 (非 Docker) 安裝 Locust。
# 安裝指令: pip install locust
# 執行後請開啟瀏覽器至 http://localhost:8089
load-test:
	@echo "==> 啟動 Locust 壓力測試..."
	@locust -f locustfile.py

# 建立用於金絲雀測試的樣本資料。
create-canary:
	@echo "==> 建立金絲雀測試樣本資料..."
	@$(MAKE) -s _run_in_worker script_cmd="scripts.create_canary_sample"

# 根據模板重新產生 README.md 文件。
generate-readme:
	@echo "==> 重新產生 README.md..."
	@$(MAKE) -s _run_in_worker script_cmd="scripts.generate_readme"

# `generate-readme` 的簡短別名
gen-readme: generate-readme

# 重設本地開發資料庫 (此操作會刪除所有資料)。
reset-db:
	@echo "==> 警告：即將重設本地開發資料庫..."
	@$(MAKE) -s _run_in_worker script_cmd="scripts.reset_db --yes"


# --- 內部輔助任務 (Internal Helper Targets) ---
# 這些任務不應由使用者直接呼叫。
.PHONY: _run_in_worker _run_in_worker_xvfb

_run_in_worker:
	@$(_WORKER_CMD)

_run_in_worker_xvfb:
	@$(_WORKER_CMD_XVFB)
