# tests/test_tasks.py

from unittest.mock import patch
import pytest
from app import tasks
from app.exceptions import RetryableScraperError, FatalScraperError, GameNotFinalError


@pytest.fixture
def mock_task_dependencies(monkeypatch):
    """
    【修正】模擬 tasks 模組的所有外部依賴。
    修正 patch 的目標路徑，指向被 import 的模組。
    """
    mocks = {
        "scraper": patch("app.tasks.scraper").start(),
        "logger": patch("app.tasks.logger").start(),
        # 【修正】Patch 函式被查找的路徑 (lookup path)，而不是它被定義的路徑
        "schedule_scraper": patch("app.core.schedule_scraper", create=True).start(),
        "setup_scheduler": patch("app.scheduler.setup_scheduler", create=True).start(),
    }
    yield mocks
    patch.stopall()


# --- 測試 should_retry_scraper_task 輔助函式 ---


def test_should_retry_returns_true_for_retryable_error():
    """測試對於 RetryableScraperError，重試判斷函式應回傳 True。"""
    assert tasks.should_retry_scraper_task(0, RetryableScraperError()) is True


@pytest.mark.parametrize(
    "exception", [FatalScraperError(), GameNotFinalError(), ValueError()]
)
def test_should_retry_returns_false_for_non_retryable_errors(exception):
    """測試對於所有非 Retryable 的錯誤，重試判斷函式應回傳 False。"""
    assert tasks.should_retry_scraper_task(0, exception) is False


# --- 測試 task_scrape_single_day ---


def test_task_scrape_single_day_success(mock_task_dependencies):
    """測試單日爬蟲任務的成功路徑。"""
    mock_scraper = mock_task_dependencies["scraper"]
    date_str = "2025-07-16"
    games_data = [{"id": 1}]

    tasks.task_scrape_single_day(date_str, games_data)

    mock_scraper.scrape_single_day.assert_called_once_with(date_str, games_data)


def test_task_scrape_single_day_propagates_retryable_error(
    mock_task_dependencies,
):
    """
    【修正】測試單日爬蟲在遇到 RetryableScraperError 時，會將錯誤向上傳遞。
    Dramatiq 的 middleware 會捕捉此錯誤並觸發重試，但單元測試只驗證錯誤被正確拋出。
    """
    mock_scraper = mock_task_dependencies["scraper"]
    mock_scraper.scrape_single_day.side_effect = RetryableScraperError("Network issue")

    # 驗證底層的 RetryableScraperError 被拋出，而非 dramatiq.errors.Retry
    with pytest.raises(RetryableScraperError, match="Network issue"):
        tasks.task_scrape_single_day("2025-07-16", [])


@pytest.mark.parametrize(
    "error", [FatalScraperError("Fatal issue"), GameNotFinalError("Game not final")]
)
def test_task_scrape_single_day_logs_and_stops_on_fatal_error(
    mock_task_dependencies, error
):
    """測試單日爬蟲在遇到致命錯誤時會記錄日誌並終止，不重試。"""
    mock_scraper = mock_task_dependencies["scraper"]
    mock_logger = mock_task_dependencies["logger"]
    mock_scraper.scrape_single_day.side_effect = error

    # 執行任務，不應拋出任何異常
    tasks.task_scrape_single_day("2025-07-16", [])

    mock_logger.error.assert_called_once()
    assert "發生不可重試的錯誤" in mock_logger.error.call_args[0][0]


# --- 測試 task_update_schedule_and_reschedule ---


def test_task_update_schedule_success(mock_task_dependencies):
    """【修正】測試賽程更新任務的成功路徑。"""
    mock_schedule_scraper = mock_task_dependencies["schedule_scraper"]
    mock_setup_scheduler = mock_task_dependencies["setup_scheduler"]

    tasks.task_update_schedule_and_reschedule()

    mock_schedule_scraper.scrape_cpbl_schedule.assert_called_once_with(
        2025, 3, 11, include_past_games=True
    )
    mock_setup_scheduler.assert_called_once()


def test_task_update_schedule_propagates_retryable_error(mock_task_dependencies):
    """【修正】測試賽程更新任務在遇到 RetryableScraperError 時會向上傳遞錯誤。"""
    mock_schedule_scraper = mock_task_dependencies["schedule_scraper"]
    mock_schedule_scraper.scrape_cpbl_schedule.side_effect = RetryableScraperError(
        "Schedule page timeout"
    )

    with pytest.raises(RetryableScraperError, match="Schedule page timeout"):
        tasks.task_update_schedule_and_reschedule()


def test_task_update_schedule_stops_on_fatal_error(mock_task_dependencies):
    """【修正】測試賽程更新任務在遇到致命錯誤時會記錄日誌並終止。"""
    mock_schedule_scraper = mock_task_dependencies["schedule_scraper"]
    mock_logger = mock_task_dependencies["logger"]
    mock_schedule_scraper.scrape_cpbl_schedule.side_effect = FatalScraperError(
        "Schedule page format changed"
    )

    tasks.task_update_schedule_and_reschedule()

    mock_logger.error.assert_called_once()
    assert "發生致命錯誤" in mock_logger.error.call_args[0][0]


# --- 測試 task_scrape_entire_year ---


def test_task_scrape_entire_year_success(mock_task_dependencies):
    """測試逐年爬蟲任務的成功路徑。"""
    mock_scraper = mock_task_dependencies["scraper"]
    tasks.task_scrape_entire_year("2024")
    mock_scraper.scrape_entire_year.assert_called_once_with("2024")


def test_task_scrape_entire_year_catches_and_logs_exception(mock_task_dependencies):
    """測試逐年爬蟲任務會捕捉並記錄一般性的錯誤。"""
    mock_scraper = mock_task_dependencies["scraper"]
    mock_logger = mock_task_dependencies["logger"]
    mock_scraper.scrape_entire_year.side_effect = ValueError("Unexpected issue")

    # 逐年爬蟲有自己的錯誤處理，不應讓錯誤拋出 actor
    tasks.task_scrape_entire_year("2024")

    mock_logger.error.assert_called_once()
    assert "發生嚴重錯誤" in mock_logger.error.call_args[0][0]
