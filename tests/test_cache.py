# tests/test_cache.py

import json
import pytest
from unittest.mock import MagicMock

import redis.exceptions
from fastapi.encoders import jsonable_encoder

# 待測試的模組
from app import cache

# --- 測試 _generate_cache_key 輔助函式 ---


def mock_request_with_params(query_params: dict, path_params: dict = None) -> MagicMock:
    """【修改】建立一個帶有指定查詢和路徑參數的模擬 Request 物件。"""
    if path_params is None:
        path_params = {}
    request = MagicMock()
    # 為了測試，將 query_params 和 path_params 模擬為字典即可
    request.query_params = query_params
    request.path_params = path_params
    return request


def mock_func():
    """一個用於測試的模擬函式。"""
    pass


def test_generate_cache_key_no_params():
    """測試在沒有任何參數時，快取鍵的產生是否正確。"""
    request = mock_request_with_params(query_params={})
    expected_key = "test_cache:mock_func:"
    assert cache._generate_cache_key(mock_func, request) == expected_key


def test_generate_cache_key_with_query_params():
    """測試只帶有查詢參數時，快取鍵的產生是否正確。"""
    request = mock_request_with_params(
        query_params={"player": "王柏融", "year": "2024"}
    )
    # 參數應按字母順序排序
    expected_key = "test_cache:mock_func:player=王柏融&year=2024"
    assert cache._generate_cache_key(mock_func, request) == expected_key


def test_generate_cache_key_param_order_agnostic():
    """測試不同順序的查詢參數是否能產生相同的快取鍵。"""
    request1 = mock_request_with_params(query_params={"b": "2", "a": "1"})
    request2 = mock_request_with_params(query_params={"a": "1", "b": "2"})

    key1 = cache._generate_cache_key(mock_func, request1)
    key2 = cache._generate_cache_key(mock_func, request2)

    assert key1 == key2
    assert key1 == "test_cache:mock_func:a=1&b=2"


def test_generate_cache_key_with_path_param_only():
    """【新增】測試只包含路徑參數時，快取鍵的產生是否正確 (重現 bug 的情境)。"""
    request = mock_request_with_params(
        query_params={}, path_params={"player_name": "陳傑憲"}
    )
    expected_key = "test_cache:mock_func:player_name=陳傑憲"
    assert cache._generate_cache_key(mock_func, request) == expected_key


def test_generate_cache_key_with_path_and_query_params():
    """【新增】測試同時包含路徑參數和查詢參數時，快取鍵的產生是否正確。"""
    request = mock_request_with_params(
        query_params={"year": "2024"}, path_params={"player_name": "王柏融"}
    )
    # 所有參數應合併並按字母順序排序
    expected_key = "test_cache:mock_func:player_name=王柏融&year=2024"
    assert cache._generate_cache_key(mock_func, request) == expected_key


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
    live_result = {"data": "live_result"}
    original_func = MagicMock(return_value=live_result)

    @cache.cache()
    def cached_endpoint(request: MagicMock):
        return original_func(request=request)

    # 執行
    request = mock_request_with_params(query_params={"id": "123"})
    result = cached_endpoint(request=request)

    # 驗證
    assert result == live_result
    original_func.assert_called_once()
    mock_redis.get.assert_called_once()

    # 驗證 setex 被呼叫，且傳入的值是經過 jsonable_encoder 處理的
    expected_key = "test_cache:cached_endpoint:id=123"
    expected_value = json.dumps(jsonable_encoder(live_result))
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
    request = mock_request_with_params(query_params={"id": "123"})
    result = cached_endpoint(request=request)

    # 驗證
    assert result == cached_data
    original_func.assert_not_called()  # 驗證原始函式未被執行
    mock_redis.get.assert_called_once()
    mock_redis.setex.assert_not_called()  # 驗證沒有再次寫入快取


def test_cache_redis_operational_error(mock_redis):
    """
    測試當 Redis 在操作中 (get/set) 失敗時，裝飾器是否能優雅地失敗。
    預期行為：
    1. 原始函式被呼叫一次。
    2. 程式不應崩潰，應正常回傳原始函式的結果。
    """
    # 準備
    mock_redis.get.side_effect = redis.exceptions.RedisError("Operation failed")
    original_func = MagicMock(return_value={"data": "live_result_from_fallback"})

    @cache.cache()
    def cached_endpoint(request: MagicMock):
        return original_func(request=request)

    # 執行
    request = mock_request_with_params(query_params={"id": "123"})
    result = cached_endpoint(request=request)

    # 驗證
    assert result == {"data": "live_result_from_fallback"}
    original_func.assert_called_once()
    mock_redis.get.assert_called_once()  # 驗證嘗試讀取快取
    mock_redis.setex.assert_not_called()  # 驗證未嘗試寫入快取


def test_cache_disabled_if_redis_fails_on_startup(mocker):
    """
    測試當 Redis 在啟動時就連線失敗 (redis_client is None) 的情境。
    預期行為：
    1. 裝飾器直接執行原始函式，完全跳過所有 Redis 操作。
    """
    # 準備
    mocker.patch("app.cache.redis_client", None)  # 模擬 redis_client 為 None
    original_func = MagicMock(return_value={"data": "live_result_redis_disabled"})

    @cache.cache()
    def cached_endpoint(request: MagicMock):
        return original_func(request=request)

    # 執行
    request = mock_request_with_params(query_params={"id": "123"})
    result = cached_endpoint(request=request)

    # 驗證
    assert result == {"data": "live_result_redis_disabled"}
    original_func.assert_called_once()
