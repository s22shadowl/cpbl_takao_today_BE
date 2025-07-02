# reset_db.py
#
# 這個腳本會連接到資料庫，刪除所有由 SQLAlchemy 模型定義的表格，
# 然後再重新建立它們，以達到清空資料的效果。
#
# 使用方法 (在啟用 venv 的 WSL 終端機中):
# python reset_db.py --yes

import logging
import argparse
from app.db import engine, Base
from app.logging_config import setup_logging
# 關鍵：我們需要先導入 models，讓 Base 知道有哪些表格需要被操作
# 我們用 # noqa: F401 來告訴 linter，這個匯入雖然看起來沒被使用，但卻是必要的。
from app import models  # noqa: F401

# 在模組載入時就套用日誌設定
setup_logging()
# 使用標準方式取得 logger
logger = logging.getLogger(__name__)

def reset_db():
    """
    刪除並重新建立所有資料庫表格。
    """
    try:
        logger.info("正在連接到資料庫並準備刪除所有表格...")
        # Base.metadata.drop_all 會依照依賴順序，安全地刪除所有表格
        Base.metadata.drop_all(bind=engine)
        logger.info("所有舊表格已成功刪除。")

        logger.info("正在重新建立所有表格...")
        # Base.metadata.create_all 會重新建立所有表格
        Base.metadata.create_all(bind=engine)
        logger.info("所有表格已成功重新建立。資料庫現在是空的。")

    except Exception as e:
        logger.error(f"重設資料庫時發生錯誤: {e}", exc_info=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="重設資料庫，此操作會刪除所有資料並重建表格。",
        epilog="請加上 --yes 旗標來確認執行此破壞性操作。"
    )
    parser.add_argument(
        '--yes',
        '-y',
        action='store_true',
        help='自動確認操作，不會出現互動式提示。'
    )
    args = parser.parse_args()

    if args.yes:
        logger.info("已接收到 --yes 確認旗標，開始執行資料庫重設...")
        reset_db()
    else:
        logger.warning("這是一個破壞性操作，將會清空所有資料。")
        logger.warning("請加上 --yes 或 -y 旗標來確認執行。")
        logger.warning("範例: python reset_database.py --yes")