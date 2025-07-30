# app/logging_config.py

import logging.config
from pathlib import Path
from pythonjsonlogger.json import JsonFormatter

from app.utils.request_context import request_id_var


# 建立一個自訂的 Formatter，它會自動加入 request_id
class CustomJsonFormatter(JsonFormatter):
    def add_fields(self, log_record, record, message_dict):
        super(CustomJsonFormatter, self).add_fields(log_record, record, message_dict)
        # 從 contextvars 獲取 request_id
        request_id = request_id_var.get()
        if request_id:
            # 如果存在，就將它加入到輸出的 JSON 欄位中
            log_record["request_id"] = request_id


# 使用 pathlib 定義基礎路徑與日誌目錄
BASE_DIR = Path(__file__).parent.parent
LOG_DIR = BASE_DIR / "logs"

# 定義日誌設定字典
LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "%(asctime)s - [%(levelname)s] - %(name)s: %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
        "json": {
            # 使用我們自訂的 Formatter
            "()": "app.logging_config.CustomJsonFormatter",
            # --- 修改: 移除固定的 format 字串，讓 formatter 自動包含所有欄位 ---
            # 當錯誤發生時，這會自動包含結構化的 exc_info 和 exc_text。
            "rename_fields": {
                "asctime": "timestamp",
                "levelname": "level",
                "name": "logger_name",
            },
            "datefmt": "%Y-%m-%dT%H:%M:%S%z",
        },
    },
    "handlers": {
        "console": {
            "level": "INFO",
            "class": "logging.StreamHandler",
            "formatter": "json",
        },
        "file": {
            "level": "INFO",
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "standard",
            "filename": LOG_DIR / "app.log",
            "maxBytes": 1024 * 1024 * 5,  # 5 MB
            "backupCount": 3,
            "encoding": "utf-8",
        },
    },
    "root": {
        "handlers": ["console", "file"],
        "level": "INFO",
    },
}


def setup_logging():
    """
    套用全域日誌設定。
    在套用設定前，會先確保日誌目錄存在。
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.config.dictConfig(LOGGING_CONFIG)
