# app/core/constants.py

"""
本檔案用於存放整個應用程式中可複用的常數，特別是與棒球業務邏輯相關的分類。
"""

# ==============================================================================
# 打席結果分類 (At-Bat Result Categories) - 來源: Box Score 短摘要
# 使用 set 以利於快速查詢與集合運算。
# ==============================================================================

# --- 安打類 (Hits) ---
HITS = {
    "一安",
    "二安",
    "三安",
    "內安",
    "內二",
    "內三",
    "場安",
    "場二",
    "場三",
    "全打",
    "內全",
}

# --- 保送類 (Walks) ---
WALKS = {"四壞", "故四", "死球"}

# --- 犧牲打類 (Sacrifices) ---
SACRIFICES = {"犧短", "犧飛", "界犧飛"}

# --- 出局類 (Outs) ---
# 可根據未來分析需求擴充
STRIKEOUTS = {"三振"}
GIDP = {"雙殺", "三殺"}
OUTS_IN_PLAY = {
    "投滾",
    "投飛",
    "捕滾",
    "捕飛",
    "一滾",
    "一飛",
    "二滾",
    "二飛",
    "三滾",
    "三飛",
    "游滾",
    "游飛",
    "左滾",
    "左飛",
    "中滾",
    "中飛",
    "右滾",
    "右飛",
    "內飛",
    "界飛",
}
ALL_OUTS = STRIKEOUTS | GIDP | OUTS_IN_PLAY

# --- 其他上壘類型 (Other On-Base Events) ---
FIELDERS_CHOICE = {"野選"}
ERRORS = {
    "投失",
    "捕失",
    "一失",
    "二失",
    "三失",
    "游失",
    "左失",
    "中失",
    "右失",
    "雙誤",
    "犧短誤",
    "犧飛誤",
}


# ==============================================================================
# 邏輯組合分類 (Logical Combined Categories)
# ==============================================================================

# --- 定義 B: 連續上壘 (Consecutive On Base) ---
ON_BASE_RESULTS = HITS | WALKS

# --- 定義 C: 連續推進 (Consecutive Advancements) ---
ADVANCEMENT_RESULTS = ON_BASE_RESULTS | SACRIFICES


# ==============================================================================
# 【新增】關鍵字定義 (用於解析完整文字描述) - 來源: Live 直播文字
# ==============================================================================

# --- 用於 parsers.live._determine_result_details ---
PARSER_ON_BASE_KEYWORDS = {"安打", "保送", "四壞", "觸身", "全壘打"}
PARSER_OUT_KEYWORDS = {"三振", "出局", "雙殺", "封殺"}
PARSER_SACRIFICE_KEYWORDS = {"犧牲"}
PARSER_FC_KEYWORDS = {"野手選擇"}
PARSER_ERROR_KEYWORDS = {"失誤"}

# --- 用於 state_machine._update_runners_state ---
STATE_MACHINE_HITTER_TO_FIRST_KEYWORDS = {"一壘安打", "內野安打", "四壞球", "觸身死球"}
