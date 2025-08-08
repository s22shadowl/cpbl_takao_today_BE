# locustfile.py

import random
import os
from locust import HttpUser, task, between

# --- 測試數據設定 ---
# TODO: 請將以下列表中的數據，替換為你資料庫中實際存在的有效資料。
# 測試數據越豐富，壓力測試的結果越能反映真實情況。
TEST_DATA = {
    "game_ids": [1, 2, 3, 4, 5],  # 請填入有效的 game_id
    "player_names": [
        "王柏融",
        "吳念庭",
        "魔鷹",
        "曾子祐",
        "王博玄",
    ],  # 請填入有效的球員名稱
    "streak_player_names": ["王柏融", "吳念庭", "魔鷹"],
    "min_length": [2, 3],
    "streak_definitions": [
        "consecutive_on_base",
        "consecutive_hits",
        "consecutive_at_bats_with_rbi",
    ],
    "situations": ["bases_empty", "scoring_position", "bases_loaded"],
}
# --- 測試數據設定結束 ---


class CPBLApiUser(HttpUser):
    """
    模擬 API 使用者的行為。
    """

    # --- 開始修改 ---
    # 指定要測試的目標主機。因為我們的 API 運行在 Docker 中，
    # 且 docker-compose.yml 將容器的 8000 port 映射到本地，
    # 所以這裡使用 localhost:8000。
    host = "http://localhost:8000"

    # 測試執行間的等待時間，模擬真實使用者不會連續不斷發送請求
    wait_time = between(1, 5)  # 每個任務執行後隨機等待 1-5 秒

    def on_start(self):
        """
        在每個模擬使用者開始測試前執行。
        設定必要的 request headers。
        """
        # 從環境變數讀取 API_KEY，若不存在則使用預設值
        self.api_key = os.environ.get("API_KEY", "your_secret_api_key_here")
        self.client.headers = {"X-API-Key": self.api_key}

    @task(10)
    def get_game_details(self):
        """
        測試「單一主鍵查詢」: 取得比賽詳細資料。
        權重設為 10，表示此任務的執行頻率較高。
        """
        if not TEST_DATA["game_ids"]:
            return
        game_id = random.choice(TEST_DATA["game_ids"])
        self.client.get(
            f"/api/games/details/{game_id}",
            name="/api/games/details/[game_id]",  # 在 Locust 報告中將此類請求歸為一組
        )

    @task(5)
    def get_player_stats_history(self):
        """
        測試「範圍/列表查詢」: 取得球員歷史數據。
        權重設為 5。
        """
        if not TEST_DATA["player_names"]:
            return
        player_name = random.choice(TEST_DATA["player_names"])
        self.client.get(
            f"/api/players/{player_name}/stats/history",
            name="/api/players/[player_name]/stats/history",
        )

    @task(2)
    def get_streaks(self):
        """
        (已修正) 測試「複雜聚合/分析查詢」: 取得連線紀錄。
        權重設為 2，表示這是計算成本較高、頻率較低的請求。
        """
        if not TEST_DATA["player_names"] or not TEST_DATA["streak_definitions"]:
            return

        player_name = random.choice(TEST_DATA["streak_player_names"])
        min_length = random.choice(TEST_DATA["min_length"])
        definition = random.choice(TEST_DATA["streak_definitions"])

        # 使用正確的參數 definition_name 和 player_names
        self.client.get(
            f"/api/analysis/streaks?definition={definition}&min_length={min_length}&player_names={player_name}",
            name="/api/analysis/streaks",
        )

    @task(3)
    def get_situational_at_bats(self):
        """
        (已修正) 測試「複雜聚合/分析查詢」: 取得情境打席數據。
        權重設為 3。
        """
        if not TEST_DATA["player_names"] or not TEST_DATA["situations"]:
            return

        player_name = TEST_DATA["player_names"]
        situation = random.choice(TEST_DATA["situations"])

        # 新增必要的 situation 查詢參數
        self.client.get(
            f"/api/analysis/players/{player_name}/situational-at-bats?situation={situation}",
            name="/api/analysis/players/[player_name]/situational-at-bats",
        )
