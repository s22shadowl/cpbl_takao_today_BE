# init_database.py (修正後)

from app.db import init_db

# 關鍵修正：在呼叫 init_db() 之前，我們需要先導入 models 模組。
# 這樣一來，所有在 app/models.py 中繼承自 Base 的類別，
# 就會被 SQLAlchemy 自動註冊到 Base.metadata 中。
from app import models

print("準備開始初始化資料庫...")

# 現在執行的 init_db() 就知道要建立哪些表格了
init_db()

print("腳本執行完畢。")