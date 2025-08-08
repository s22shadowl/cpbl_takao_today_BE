# tests/test_cache.py

import json
import pytest
from unittest.mock import MagicMock

import redis.exceptions

# 待測試的模組
from app import cache

# --- 測試 _generate_cache_key 輔助函式 ---


def mock_request_with_params(params: dict) -> MagicMock:
    """建立一個帶有指定查詢參數的模擬 Request 物件。"""
    request = MagicMock()
    request.query_params.items.return_value = params.items()
    return request


def mock_func():
    """一個用於測試的模擬函式。"""
    pass


def test_generate_cache_key_no_params():
    """測試在沒有查詢參數時，快取鍵的產生是否正確。"""
    request = mock_request_with_params({})
    expected_key = "test_cache:mock_func:"
    assert cache._generate_cache_key(mock_func, request) == expected_key


def test_generate_cache_key_with_params():
    """測試帶有查詢參數時，快取鍵的產生是否正確。"""
    request = mock_request_with_params({"player": "王柏融", "year": "2024"})
    # 參數應按字母順序排序
    expected_key = "test_cache:mock_func:player=王柏融&year=2024"
    assert cache._generate_cache_key(mock_func, request) == expected_key


def test_generate_cache_key_param_order_agnostic():
    """測試不同順序的查詢參數是否能產生相同的快取鍵。"""
    request1 = mock_request_with_params({"b": "2", "a": "1"})
    request2 = mock_request_with_params({"a": "1", "b": "2"})

    key1 = cache._generate_cache_key(mock_func, request1)
    key2 = cache._generate_cache_key(mock_func, request2)

    assert key1 == key2
    assert key1 == "test_cache:mock_func:a=1&b=2"


# --- 測試 @cache 裝飾器 ---


@pytest.fixture
def mock_redis(mocker):
    """一個模擬 redis_client 的 pytest fixture。"""
    return mocker.patch("app.cache.redis_client")


def test_cache_miss(mock_redis):
    """
    測試快取未命中 (Cache Miss) 的情境。
    預期行為：
    1. 原始函式被呼叫一次。
    2. 函式結果被寫入 Redis。
    """
    # 準備
    mock_redis.get.return_value = None  # 模擬 Redis 中沒有資料
    original_func = MagicMock(return_value={"data": "live_result"})

    @cache.cache()
    def cached_endpoint(request: MagicMock):
        return original_func(request=request)

    # 執行
    request = mock_request_with_params({"id": "123"})
    result = cached_endpoint(request=request)

    # 驗證
    assert result == {"data": "live_result"}
    original_func.assert_called_once()
    mock_redis.get.assert_called_once()

    # 驗證 setex 被呼叫，且傳入的參數正確
    expected_key = "test_cache:cached_endpoint:id=123"
    expected_value = json.dumps({"data": "live_result"}, default=str)
    mock_redis.setex.assert_called_once_with(expected_key, 3600 * 24, expected_value)


def test_cache_hit(mock_redis):
    """
    測試快取命中 (Cache Hit) 的情境。
    預期行為：
    1. 原始函式完全不被呼叫。
    2. 直接回傳從 Redis 中讀取的資料。
    """
    # 準備
    cached_data = {"data": "cached_result"}
    mock_redis.get.return_value = json.dumps(cached_data)  # 模擬 Redis 中有資料
    original_func = MagicMock()

    @cache.cache()
    def cached_endpoint(request: MagicMock):
        return original_func(request=request)

    # 執行
    request = mock_request_with_params({"id": "123"})
    result = cached_endpoint(request=request)

    # 驗證
    assert result == cached_data
    original_func.assert_not_called()  # 驗證原始函式未被執行
    mock_redis.get.assert_called_once()
    mock_redis.setex.assert_not_called()  # 驗證沒有再次寫入快取


def test_cache_redis_connection_error(mock_redis):
    """
    測試當 Redis 連線失敗時，裝飾器是否能優雅地失敗。
    預期行為：
    1. 原始函式被呼叫一次。
    2. 程式不應崩潰，應正常回傳原始函式的結果。
    """
    # 準備
    mock_redis.ping.side_effect = redis.exceptions.ConnectionError
    original_func = MagicMock(return_value={"data": "live_result_from_fallback"})

    @cache.cache()
    def cached_endpoint(request: MagicMock):
        return original_func(request=request)

    # 執行
    request = mock_request_with_params({"id": "123"})
    result = cached_endpoint(request=request)

    # 驗證
    assert result == {"data": "live_result_from_fallback"}
    original_func.assert_called_once()
    mock_redis.get.assert_not_called()  # 驗證未嘗試讀取快取
    mock_redis.setex.assert_not_called()  # 驗證未嘗試寫入快取
