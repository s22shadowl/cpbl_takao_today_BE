# run_task_locally.py
#
# 這是一個專為在 Windows 本地開發環境下測試背景任務而設計的腳本。
# 它會直接導入並執行任務函式，繞開在 Windows 上有問題的 Dramatiq Worker 環境。
#
# 使用方法:
# python run_task_locally.py

import logging

def main():
    """
    主執行函式。
    """
    print("--- 本地任務執行腳本 ---")
    print("正在導入任務...")
    
    # 我們從 app.tasks 導入我們想測試的任務函式
    # 注意：我們只導入函式本身，而不是 dramatiq.actor 物件
    from app.tasks import task_update_schedule_and_reschedule

    print("任務導入成功，準備直接執行任務邏輯...")
    
    # 直接呼叫任務函式
    # 這模擬了 Dramatiq Worker 在接收到訊息後所做的事情
    task_update_schedule_and_reschedule.fn()

    print("--- 本地任務執行完畢 ---")


if __name__ == "__main__":
    # 設定日誌，以便看到爬蟲的詳細輸出
    logging.basicConfig(
        level=logging.INFO, 
        format='%(asctime)s - %(levelname)s - %(module)s - %(message)s'
    )
    main()
