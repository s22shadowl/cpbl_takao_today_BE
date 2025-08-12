# tests/test_tasks.py

from unittest.mock import patch, ANY, MagicMock
import pytest
from freezegun import freeze_time
from datetime import date, datetime

from requests.exceptions import RequestException
from app import tasks
from app.exceptions import RetryableScraperError, FatalScraperError, GameNotFinalError
from app.config import settings


@pytest.fixture
def mock_task_dependencies(monkeypatch):
    """
    模擬 tasks 模組的所有外部依賴，確保測試在隔離環境中運行。
    """
    mocks = {
        "scraper": patch("app.tasks.scraper").start(),
        "logger": patch("app.tasks.logger").start(),
        "schedule_scraper": patch("app.core.schedule_scraper", create=True).start(),
        "requests_post": patch("app.tasks.requests.post").start(),
        "SessionLocal": patch("app.tasks.SessionLocal").start(),
        "crud_games": patch("app.tasks.crud_games").start(),
        # [新增] 模擬新的依賴
        "fetcher": patch("app.tasks.fetcher").start(),
        "schedule": patch("app.tasks.schedule").start(),
        "task_scrape_single_day_send": patch(
            "app.tasks.task_scrape_single_day.send"
        ).start(),
    }

    # 設定 SessionLocal 的 mock 返回值
    mock_db_session = MagicMock()
    mocks["SessionLocal"].return_value = mock_db_session

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


# --- 測試 task_run_daily_crawl ---


@freeze_time("2025-08-11")
def test_task_run_daily_crawl_triggers_scrape_when_games_found(mock_task_dependencies):
    """測試當天有比賽時，task_run_daily_crawl 會觸發單日爬蟲任務。"""
    mock_crud_games = mock_task_dependencies["crud_games"]
    mock_logger = mock_task_dependencies["logger"]
    mock_send = mock_task_dependencies["task_scrape_single_day_send"]

    today_date_obj = date.today()
    today_str = today_date_obj.strftime("%Y-%m-%d")

    # [修正] 建立一個包含所有必要屬性的 mock game 物件
    mock_game = MagicMock()
    mock_game.game_id = "G500"
    mock_game.game_date = today_date_obj
    mock_game.game_time = "17:05"
    mock_game.home_team = "兄弟"
    mock_game.away_team = "桃猿"
    mock_game.venue = "洲際"
    mock_game.status = "Scheduled"
    mock_crud_games.get_games_by_date.return_value = [mock_game]

    tasks.task_run_daily_crawl()

    mock_crud_games.get_games_by_date.assert_called_once_with(ANY, today_date_obj)
    mock_logger.info.assert_any_call(
        f"[Daily Crawl] Found 1 game(s) for {today_str}. Triggering scrape task."
    )

    # [修正] 驗證傳遞給 send 的資料結構完全符合主程式碼的定義
    expected_game_data = [
        {
            "cpbl_game_id": "G500",
            "game_date": today_str,
            "game_time": "17:05",
            "home_team": "兄弟",
            "away_team": "桃猿",
            "venue": "洲際",
            "status": "Scheduled",
        }
    ]
    mock_send.assert_called_once_with(today_str, expected_game_data)


@freeze_time("2025-08-11")
def test_task_run_daily_crawl_skips_when_no_games_found(mock_task_dependencies):
    """測試當天沒有比賽時，task_run_daily_crawl 會跳過並記錄日誌。"""
    mock_crud_games = mock_task_dependencies["crud_games"]
    mock_logger = mock_task_dependencies["logger"]
    mock_send = mock_task_dependencies["task_scrape_single_day_send"]

    mock_crud_games.get_games_by_date.return_value = []

    tasks.task_run_daily_crawl()

    mock_crud_games.get_games_by_date.assert_called_once_with(ANY, date.today())
    today_str = date.today().strftime("%Y-%m-%d")
    mock_logger.info.assert_any_call(
        f"[Daily Crawl] No games scheduled for {today_str}. Skipping."
    )
    mock_send.assert_not_called()


@freeze_time("2025-08-11")
def test_task_run_daily_crawl_logs_error_on_db_exception(mock_task_dependencies):
    """測試當資料庫查詢發生例外時，task_run_daily_crawl 會記錄錯誤。"""
    mock_crud_games = mock_task_dependencies["crud_games"]
    mock_logger = mock_task_dependencies["logger"]
    mock_send = mock_task_dependencies["task_scrape_single_day_send"]

    mock_crud_games.get_games_by_date.side_effect = Exception("DB connection failed")

    tasks.task_run_daily_crawl()

    mock_crud_games.get_games_by_date.assert_called_once_with(ANY, date.today())
    mock_logger.error.assert_called_once()
    assert (
        "An error occurred during daily crawl check"
        in mock_logger.error.call_args[0][0]
    )
    mock_send.assert_not_called()


# --- 測試 task_scrape_single_day ---


def test_task_scrape_single_day_with_provided_games(mock_task_dependencies):
    """測試當提供賽程時，單日爬蟲任務的成功路徑。"""
    mock_scraper = mock_task_dependencies["scraper"]
    mock_fetcher = mock_task_dependencies["fetcher"]
    date_str = "2025-07-16"
    games_data = [{"id": 1}]

    tasks.task_scrape_single_day(date_str, games_data)

    mock_scraper.scrape_single_day.assert_called_once_with(date_str, games_data)
    # 驗證在提供賽程時，不會觸發線上抓取
    mock_fetcher.fetch_schedule_page.assert_not_called()


def test_task_scrape_single_day_without_provided_games_fetches_online(
    mock_task_dependencies,
):
    """[新增] 測試未提供賽程時，任務會自行線上抓取。"""
    mock_scraper = mock_task_dependencies["scraper"]
    mock_fetcher = mock_task_dependencies["fetcher"]
    mock_schedule = mock_task_dependencies["schedule"]
    date_str = "2025-07-16"
    target_date_obj = datetime.strptime(date_str, "%Y-%m-%d")

    # 模擬線上抓取和解析的結果
    mock_fetcher.fetch_schedule_page.return_value = "<html></html>"
    # 模擬解析器回傳包含當天和其他天比賽的列表
    all_games = [
        {"game_date": "2025-07-15", "id": "G1"},
        {"game_date": "2025-07-16", "id": "G2"},
        {"game_date": "2025-07-17", "id": "G3"},
    ]
    mock_schedule.parse_schedule_page.return_value = all_games

    tasks.task_scrape_single_day(date_str=date_str, games_for_day=None)

    # 驗證呼叫了 fetcher 和 parser
    mock_fetcher.fetch_schedule_page.assert_called_once_with(
        target_date_obj.year, target_date_obj.month
    )
    mock_schedule.parse_schedule_page.assert_called_once_with(
        "<html></html>", target_date_obj.year
    )

    # 驗證 scraper.scrape_single_day 只被傳入了篩選後的當天比賽
    expected_filtered_games = [{"game_date": "2025-07-16", "id": "G2"}]
    mock_scraper.scrape_single_day.assert_called_once_with(
        date_str, expected_filtered_games
    )


def test_task_scrape_single_day_propagates_retryable_error(mock_task_dependencies):
    """測試單日爬蟲在遇到 RetryableScraperError 時，會將錯誤向上傳遞。"""
    mock_scraper = mock_task_dependencies["scraper"]
    mock_scraper.scrape_single_day.side_effect = RetryableScraperError("Network issue")

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

    tasks.task_scrape_single_day("2025-07-16", [])

    mock_logger.error.assert_called_once()
    assert "發生不可重試的錯誤" in mock_logger.error.call_args[0][0]


# --- 測試 task_update_schedule_and_reschedule ---


@freeze_time("2025-01-01")
def test_task_update_schedule_success(mock_task_dependencies):
    """測試賽程更新任務的成功路徑。"""
    mock_schedule_scraper = mock_task_dependencies["schedule_scraper"]

    tasks.task_update_schedule_and_reschedule()

    mock_schedule_scraper.scrape_cpbl_schedule.assert_called_once_with(
        2025,
        settings.CPBL_SEASON_START_MONTH,
        settings.CPBL_SEASON_END_MONTH,
        include_past_games=True,
    )


def test_task_update_schedule_stops_on_fatal_error(mock_task_dependencies):
    """測試賽程更新任務在遇到致命錯誤時會記錄日誌並終止。"""
    mock_schedule_scraper = mock_task_dependencies["schedule_scraper"]
    mock_logger = mock_task_dependencies["logger"]
    mock_schedule_scraper.scrape_cpbl_schedule.side_effect = FatalScraperError(
        "Schedule page format changed"
    )

    tasks.task_update_schedule_and_reschedule()

    mock_logger.error.assert_called_once()
    assert "發生致命錯誤" in mock_logger.error.call_args[0][0]


# --- 測試其他主要任務 ---


def test_task_scrape_entire_month_success(mock_task_dependencies):
    """測試逐月爬蟲任務的成功路徑。"""
    mock_scraper = mock_task_dependencies["scraper"]
    tasks.task_scrape_entire_month("2024-05")
    mock_scraper.scrape_entire_month.assert_called_once_with("2024-05")


def test_task_scrape_entire_year_success(mock_task_dependencies):
    """測試逐年爬蟲任務的成功路徑。"""
    mock_scraper = mock_task_dependencies["scraper"]
    tasks.task_scrape_entire_year("2024")
    mock_scraper.scrape_entire_year.assert_called_once_with("2024")


# --- 測試快取清除邏輯 ---


@pytest.mark.parametrize(
    "task_func, task_args",
    [
        (tasks.task_scrape_single_day, ("2025-07-16", [])),
        (tasks.task_update_schedule_and_reschedule, ()),
        (tasks.task_scrape_entire_month, ("2025-07",)),
        (tasks.task_scrape_entire_year, ("2025",)),
    ],
)
def test_tasks_trigger_cache_clear_on_success(
    mock_task_dependencies, task_func, task_args
):
    """測試所有主要任務成功後，都會呼叫 requests.post 清除快取。"""
    mock_requests_post = mock_task_dependencies["requests_post"]

    task_func(*task_args)

    expected_url = "http://web:8000/api/system/clear-cache"
    expected_headers = {"X-API-Key": settings.API_KEY}
    mock_requests_post.assert_called_once_with(
        expected_url, headers=expected_headers, timeout=10
    )


def test_task_logs_error_if_cache_clear_fails(mock_task_dependencies):
    """測試當 requests.post 拋出異常時，任務會記錄錯誤但不會失敗。"""
    mock_requests_post = mock_task_dependencies["requests_post"]
    mock_logger = mock_task_dependencies["logger"]
    mock_requests_post.side_effect = RequestException("Connection failed")

    try:
        tasks.task_scrape_single_day("2025-07-16", [])
    except Exception as e:
        pytest.fail(f"任務不應因快取清除失敗而失敗，但拋出了: {e}")

    mock_requests_post.assert_called_once()
    mock_logger.error.assert_called_once()
    assert "呼叫快取清除 API 時發生錯誤" in mock_logger.error.call_args[0][0]
