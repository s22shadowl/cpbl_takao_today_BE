# app/cache.py

import functools
import json
import logging
from typing import Callable

import redis
from fastapi import Request
from fastapi.encoders import jsonable_encoder

from .config import settings

# --- Redis Client 初始化 ---
try:
    redis_client = redis.from_url(settings.REDIS_CACHE_URL, decode_responses=True)
    redis_client.ping()
    logging.info("成功連接至 Redis 快取資料庫。")
except redis.exceptions.ConnectionError as e:
    logging.error(f"無法連接至 Redis 快取資料庫，快取功能將被禁用: {e}", exc_info=True)
    redis_client = None


def _generate_cache_key(func: Callable, request: Request) -> str:
    """
    【修正】根據我們討論的策略，產生一個唯一的快取鍵。
    格式: [module_name]:[func_name]:[sorted_all_params]
    """
    # 將路徑參數與查詢參數合併，以確保快取鍵的唯一性
    all_params = dict(request.query_params)
    all_params.update(request.path_params)

    # 排序以確保參數順序不同時，快取鍵仍然相同
    sorted_params = sorted(all_params.items())

    params_str = "&".join([f"{k}={v}" for k, v in sorted_params])
    cache_key = f"{func.__module__}:{func.__name__}:{params_str}"
    return cache_key


def cache(expire: int = 3600 * 24):  # 預設 TTL 為 24 小時
    """
    一個 FastAPI 端點的快取裝飾器。
    """

    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(request: Request, *args, **kwargs):
            if not redis_client:
                return func(request=request, *args, **kwargs)

            try:
                cache_key = _generate_cache_key(func, request)

                # 1. 嘗試從快取中讀取資料
                cached_result = redis_client.get(cache_key)
                if cached_result:
                    logging.info(f"成功命中快取: {cache_key}")
                    return json.loads(cached_result)

                # 2. 如果快取未命中，則執行原始函式
                logging.info(f"快取未命中: {cache_key}，執行原始函式。")
                result = func(request=request, *args, **kwargs)

                # 3. 將函式結果存入快取
                # 使用 jsonable_encoder 將結果轉換為 JSON 相容的格式
                json_compatible_result = jsonable_encoder(result)
                redis_client.setex(
                    cache_key, expire, json.dumps(json_compatible_result)
                )

                return result

            except redis.exceptions.RedisError as e:
                logging.warning(f"Redis 操作失敗 ({e})，跳過快取並直接執行函式。")
                return func(request=request, *args, **kwargs)

        return wrapper

    return decorator
