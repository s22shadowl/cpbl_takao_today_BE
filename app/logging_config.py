# app/logging_config.py

import logging.config
import os

# 建立 logs 資料夾 (如果不存在)
# 使用 os.path.dirname(__file__) 來確保路徑相對於目前檔案，更為穩健
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

# 使用字典來定義日誌設定，更具彈性
LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "%(asctime)s - [%(levelname)s] - %(name)s: %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },
    "handlers": {
        "console": {
            "level": "INFO",
            "class": "logging.StreamHandler",
            "formatter": "standard",
        },
        "file": {
            "level": "INFO",
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "standard",
            "filename": os.path.join(LOG_DIR, "app.log"),
            "maxBytes": 1024 * 1024 * 5,  # 5 MB
            "backupCount": 3,
            "encoding": "utf-8",
        },
    },
    # root logger 會捕捉所有未被特別指定的 logger 的日誌
    "root": {
        "handlers": ["console", "file"],
        "level": "INFO",
    },
}


def setup_logging():
    """套用全域日誌設定"""
    logging.config.dictConfig(LOGGING_CONFIG)
