# alembic/env.py

import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# 這是 Alembic 的設定物件，提供對正在使用的 .ini 檔案中值的存取。
config = context.config

# 為了 Python 的日誌記錄功能，解析設定檔。
# 這行基本上就是設定日誌記錄器。
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# --- 自訂設定 ---
# 將專案根目錄加入到 Python 路徑，以允許絕對匯入。
# 這樣我們就可以從 'app' 模組匯入。
sys.path.insert(0, os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))

# 從我們的 db 模組匯入 SQLAlchemy 的 Base 以及所有模型。
# 這對於 Alembic 的 'autogenerate' 功能偵測模型變更是至關重要的。
from app.db import Base  # noqa: E402
from app.models import (  # noqa: E402
    GameSchedule,  # noqa: F401
    GameResultDB,  # noqa: F401
    PlayerGameSummaryDB,  # noqa: F401
    AtBatDetailDB,  # noqa: F401
    PlayerSeasonStatsDB,  # noqa: F401
)

# 為 'autogenerate' 功能設定目標元數據。
target_metadata = Base.metadata

# 匯入我們的 Pydantic 設定，以取得實際的資料庫 URL。
from app.config import settings  # noqa: E402

# --- 結束自訂設定 ---


def run_migrations_offline() -> None:
    """在 'offline' 模式下運行遷移。

    此模式僅使用一個 URL 來設定 context，而不需要一個 Engine 物件。
    透過跳過 Engine 的建立，我們甚至不需要安裝資料庫驅動 (DBAPI)。

    在此模式下呼叫 context.execute() 會將給定的字串輸出到腳本中。
    """
    # 使用我們應用程式設定中的資料庫 URL
    url = settings.DATABASE_URL
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在 'online' 模式下運行遷移。

    在此情境中，我們需要建立一個 Engine，並將一個連線與 context 關聯起來。
    """
    # 從 alembic.ini 檔案建立一個設定字典，
    # 並用我們 .env 檔案中的 URL 覆寫 sqlalchemy.url
    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = settings.DATABASE_URL

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
