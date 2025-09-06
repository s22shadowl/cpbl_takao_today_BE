# app/broker_setup.py

import dramatiq
from dramatiq.brokers.redis import RedisBroker
from dramatiq.results import Results
from dramatiq.results.backends.redis import RedisBackend

from app.config import settings

# --- [修正] 不再手動建立 broker_options ---
# 完全依賴 connection URL 來傳遞所有連線資訊。
# "rediss://" 協議本身就告訴函式庫要使用 SSL。
# Dramatiq 和 redis-py 會從 URL 中自動解析所有需要的設定。

broker_url = settings.DRAMATIQ_BROKER_URL

# 1. 建立 Result Backend (不傳入 options)
result_backend = RedisBackend(url=broker_url)

# 2. 建立 Broker (不傳入 options)
broker = RedisBroker(url=broker_url)

# 3. 將 Results 中介軟體加入 Broker
broker.add_middleware(Results(backend=result_backend))

# 4. 設定全域 Broker
dramatiq.set_broker(broker)
