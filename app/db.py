import sqlite3
import os
import datetime # 雖然此檔案本身可能不用，但示意欄位型別時有用

# 資料庫檔案路徑 (確保 app/data 資料夾存在)
DATABASE_DIR = os.path.join(os.path.dirname(__file__), 'data')
DATABASE_NAME = os.path.join(DATABASE_DIR, 'cpbl_stats.db')

# 確保 data 資料夾存在
os.makedirs(DATABASE_DIR, exist_ok=True)

def get_db_connection():
    """建立並返回資料庫連線"""
    conn = sqlite3.connect(DATABASE_NAME)
    conn.row_factory = sqlite3.Row # 讓查詢結果可以透過欄位名稱存取
    return conn

def init_db():
    """初始化資料庫，建立必要的表格"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. 比賽結果表 (game_results)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS game_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cpbl_game_id TEXT UNIQUE,         -- CPBL 官網的比賽唯一ID
        game_date TEXT NOT NULL,          -- YYYY-MM-DD
        game_time TEXT,                   -- HH:MM
        home_team TEXT NOT NULL,
        away_team TEXT NOT NULL,
        home_score INTEGER,
        away_score INTEGER,
        venue TEXT,
        status TEXT,                      -- 例如: 已完成, 延賽, 進行中
        winning_pitcher TEXT,
        losing_pitcher TEXT,
        save_pitcher TEXT,
        mvp TEXT,
        game_duration TEXT,               -- 比賽耗時，例如 "3H25M"
        attendance INTEGER,               -- 觀眾人數
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(game_date, home_team, away_team) -- 防止重複記錄同一場比賽
    )
    ''')

    # 2. 球員單場比賽總結統計 (player_game_summary)
    #    儲存球員在一場特定比賽中的打擊總結數據，
    #    以及該場比賽結束後球員的累積打擊率、上壘率等。
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS player_game_summary (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        game_id INTEGER NOT NULL,              -- 外鍵，關聯到 game_results 表的 id
        player_name TEXT NOT NULL,
        team_name TEXT,                        -- 球員該場所屬隊伍
        batting_order TEXT,                    -- 棒次，例如 "第三棒", "PH" (代打)
        position TEXT,                         -- 守備位置，例如 "LF", "DH"
        
        -- 單場表現數據
        plate_appearances INTEGER DEFAULT 0,   -- 打席 PA (AB + BB + HBP + SF + SH + CI)
        at_bats INTEGER DEFAULT 0,             -- 打數 AB
        runs_scored INTEGER DEFAULT 0,         -- 得分 R
        hits INTEGER DEFAULT 0,                -- 安打 H
        doubles INTEGER DEFAULT 0,             -- 二壘安打 2B
        triples INTEGER DEFAULT 0,             -- 三壘安打 3B
        homeruns INTEGER DEFAULT 0,            -- 全壘打 HR
        rbi INTEGER DEFAULT 0,                 -- 打點 RBI
        walks INTEGER DEFAULT 0,               -- 四壞球 BB (通常包含 IBB)
        intentional_walks INTEGER DEFAULT 0,   -- 故意四壞 IBB (如果網站有分開提供)
        hit_by_pitch INTEGER DEFAULT 0,        -- 觸身球 HBP
        strikeouts INTEGER DEFAULT 0,          -- 三振 K (或 SO)
        stolen_bases INTEGER DEFAULT 0,        -- 盜壘 SB
        caught_stealing INTEGER DEFAULT 0,     -- 盜壘失敗 CS
        sacrifice_hits INTEGER DEFAULT 0,      -- 犧牲觸擊 SH
        sacrifice_flies INTEGER DEFAULT 0,     -- 犧牲飛球 SF
        gidp INTEGER DEFAULT 0,                -- 滾地球雙殺打 GIDP
        
        -- 該場比賽結束後的累積數據
        avg_cumulative REAL,                   -- 累積打擊率 AVG
        obp_cumulative REAL,                   -- 累積上壘率 OBP
        slg_cumulative REAL,                   -- 累積長打率 SLG
        ops_cumulative REAL,                   -- 累積整體攻擊指數 OPS
        
        at_bat_results_summary TEXT,           -- 逐打席結果摘要，例如 "左飛,投滾,三振,二滾,左飛"
        
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (game_id) REFERENCES game_results (id),
        UNIQUE(game_id, player_name, team_name) -- 同一場比賽同一個球員(同隊情況下)只應有一條記錄
                                                -- team_name 加入是為了處理可能的同名但不同隊球員在同一場比賽(雖然罕見)
                                                -- 或者，如果 player_name 在整個聯盟是唯一的，可以簡化
    )
    ''')

    # 3. 逐打席詳細記錄 (at_bat_details)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS at_bat_details (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        player_game_summary_id INTEGER NOT NULL, -- 外鍵，關聯到 player_game_summary 表的 id
        inning INTEGER,                          -- 第幾局 (例如 1, 9, 10 代表延長賽)
        sequence_in_game INTEGER,                -- 該球員在本場比賽的第幾次打席 (PA sequence)
        
        result_short TEXT,                       -- 簡易結果，例如 "左飛", "三振", "一壘安打"
        result_description_full TEXT,            -- 詳細結果描述 (來自範例)
        opposing_pitcher_name TEXT,              -- 對戰投手姓名
        pitch_sequence_details TEXT,             -- 好壞球詳細記錄 (來自範例，多行文本)
        
        runners_on_base_before TEXT,             -- 打擊前壘包狀況 (可選，例如 "一二壘有人")
        outs_before INTEGER,                     -- 打擊前出局數 (可選)

        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (player_game_summary_id) REFERENCES player_game_summary (id),
        UNIQUE(player_game_summary_id, sequence_in_game) -- 同一個球員的同一次打席記錄應唯一
    )
    ''')

    # 4. 球員球季累積數據表 (player_season_stats)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS player_season_stats (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        player_name TEXT NOT NULL UNIQUE,
        team_name TEXT,
        data_retrieved_date TEXT,
        -- 主要統計數據
        games_played INTEGER DEFAULT 0,
        plate_appearances INTEGER DEFAULT 0,
        at_bats INTEGER DEFAULT 0,
        runs_scored INTEGER DEFAULT 0,
        hits INTEGER DEFAULT 0,
        rbi INTEGER DEFAULT 0,
        homeruns INTEGER DEFAULT 0,
        -- 安打類型
        singles INTEGER DEFAULT 0,
        doubles INTEGER DEFAULT 0,
        triples INTEGER DEFAULT 0,
        -- 其他打擊數據
        total_bases INTEGER DEFAULT 0,
        strikeouts INTEGER DEFAULT 0,
        stolen_bases INTEGER DEFAULT 0,
        gidp INTEGER DEFAULT 0,
        sacrifice_hits INTEGER DEFAULT 0,
        sacrifice_flies INTEGER DEFAULT 0,
        -- 上壘相關
        walks INTEGER DEFAULT 0,
        intentional_walks INTEGER DEFAULT 0,
        hit_by_pitch INTEGER DEFAULT 0,
        -- 跑壘相關
        caught_stealing INTEGER DEFAULT 0,
        -- 出局分析
        ground_outs INTEGER DEFAULT 0,
        fly_outs INTEGER DEFAULT 0,
        -- 比率數據
        avg REAL,
        obp REAL,
        slg REAL,
        ops REAL,
        go_ao_ratio REAL,
        sb_percentage REAL,
        -- 指標數據
        silver_slugger_index REAL,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    
    # 可以考慮為常用的查詢欄位建立索引，以提高查詢效能
    # 例如：球員姓名、比賽日期等
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_pgs_player_name ON player_game_summary (player_name);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_gr_game_date ON game_results (game_date);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_abd_summary_id ON at_bat_details (player_game_summary_id);")


    conn.commit()
    conn.close()
    print(f"資料庫已於 {DATABASE_NAME} 初始化/更新完成。")

if __name__ == '__main__':
    # 如果直接執行此檔案，則初始化資料庫
    print(f"資料庫檔案將建立於: {DATABASE_NAME}")
    init_db()