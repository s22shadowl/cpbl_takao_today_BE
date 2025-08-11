# scripts/reset_db.py
#
# 這個腳本會連接到資料庫，刪除所有由 SQLAlchemy 模型定義的表格，
# 然後再重新建立它們，以達到清空資料的效果。
#
# 使用方法 (在啟用 venv 的 WSL 終端機中):
# python -m scripts.reset_db --yes

import logging
import argparse
from dotenv import load_dotenv
from app.logging_config import setup_logging


def main():
    """
    執行資料庫重設的主要邏輯。
    """
    # 步驟 1: 優先設定日誌系統
    setup_logging()
    logger = logging.getLogger(__name__)

    # 步驟 2: 接著載入環境變數，這必須在導入 app.db 之前完成
    logger.info("正在載入 .env 環境變數...")

    # ▼▼▼ 修改: 直接呼叫 load_dotenv() ▼▼▼
    # 這會自動從當前工作目錄尋找 .env 檔案，這是執行此類腳本的標準作法。
    if not load_dotenv():
        logger.error(
            "錯誤：在當前目錄下找不到 .env 檔案。請確認您是在專案根目錄下執行此腳本。"
        )
        exit(1)
    logger.info(".env 檔案已成功載入。")
    # ▲▲▲ 修改結束 ▲▲▲

    # 步驟 3: 現在環境變數已設定，可以安全地導入 app 相關模組
    from app.db import engine, Base

    # 關鍵：我們需要先導入 models，讓 Base 知道有哪些表格需要被操作
    # 我們用 # noqa: F401 來告訴 linter，這個匯入雖然看起來沒被使用，但卻是必要的。
    from app import models  # noqa: F401

    # 步驟 4: 執行資料庫操作
    try:
        logger.info("正在連接到資料庫並準備刪除所有表格...")
        Base.metadata.drop_all(bind=engine)
        logger.info("所有舊表格已成功刪除。")

        logger.info("正在重新建立所有表格...")
        Base.metadata.create_all(bind=engine)
        logger.info("所有表格已成功重新建立。資料庫現在是空的。")

    except Exception as e:
        logger.error(f"重設資料庫時發生錯誤: {e}", exc_info=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="重設資料庫，此操作會刪除所有資料並重建表格。",
        epilog="請加上 --yes 旗標來確認執行此破壞性操作。",
    )
    parser.add_argument(
        "--yes", "-y", action="store_true", help="自動確認操作，不會出現互動式提示。"
    )
    args = parser.parse_args()

    if args.yes:
        # 只有在確認後才執行主要邏輯
        main()
    else:
        # 在執行主要邏輯前，日誌系統可能尚未設定，但此處使用 print 或預設 logger 亦可
        print("警告: 這是一個破壞性操作，將會清空所有資料。")
        print("警告: 請加上 --yes 或 -y 旗標來確認執行。")
        print("警告: 範例: python -m scripts.reset_db --yes")
