# app/cache.py

import functools
import json
import logging
from typing import Callable

import redis
from fastapi import Request

from .config import settings

# 建立一個 Redis 連線池
# decode_responses=True 確保從 Redis 讀取的值是字串而非 bytes
redis_client = redis.from_url(settings.DRAMATIQ_BROKER_URL, decode_responses=True)


def _generate_cache_key(func: Callable, request: Request) -> str:
    """
    根據我們討論的策略，產生一個唯一的快取鍵。
    格式: [module_name]:[func_name]:[sorted_query_params]
    """
    # 1. 將查詢參數的鍵進行排序，以確保順序不同時也能命中快取
    sorted_params = sorted(request.query_params.items())

    # 2. 將排序後的參數轉換為一個緊湊的字串
    params_str = "&".join([f"{k}={v}" for k, v in sorted_params])

    # 3. 組合最終的快取鍵
    cache_key = f"{func.__module__}:{func.__name__}:{params_str}"

    return cache_key


def cache(expire: int = 3600 * 24):  # 預設 TTL 為 24 小時
    """
    一個 FastAPI 端點的快取裝飾器。
    """

    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(request: Request, *args, **kwargs):
            # 確保 Redis 服務可用
            try:
                redis_client.ping()
            except redis.exceptions.ConnectionError:
                logging.warning("Redis 連線失敗，跳過快取並直接執行函式。")
                return func(request=request, *args, **kwargs)

            cache_key = _generate_cache_key(func, request)

            # 1. 嘗試從快取中讀取資料
            cached_result = redis_client.get(cache_key)
            if cached_result:
                logging.info(f"成功命中快取: {cache_key}")
                # 將 JSON 字串轉換回 Python 物件並回傳
                return json.loads(cached_result)

            # 2. 如果快取未命中，則執行原始函式
            logging.info(f"快取未命中: {cache_key}，執行原始函式。")
            result = func(request=request, *args, **kwargs)

            # 3. 將函式結果存入快取
            try:
                # 將 Python 物件轉換為 JSON 字串進行儲存
                redis_client.setex(cache_key, expire, json.dumps(result, default=str))
            except Exception as e:
                logging.error(f"寫入 Redis 快取時發生錯誤: {e}", exc_info=True)

            return result

        return wrapper

    return decorator
