# tests/test_run_scraper.py

import pytest
from unittest.mock import patch

# 導入我們重構後的可測試主程式
from run_scraper import main

# 使用 pytest.mark.parametrize 來組織測試案例，提高可讀性和可維護性
@pytest.mark.parametrize(
    "command_line_args, expected_function_call",
    [
        # 測試 daily 模式
        (["daily"], "scraper.scrape_single_day"),
        (["daily", "2025-06-21"], "scraper.scrape_single_day"),
        # 測試 monthly 模式
        (["monthly"], "scraper.scrape_entire_month"),
        (["monthly", "2025-06"], "scraper.scrape_entire_month"),
        # 測試 yearly 模式
        (["yearly"], "scraper.scrape_entire_year"),
        (["yearly", "2024"], "scraper.scrape_entire_year"),
    ],
    ids=[
        "daily_default",
        "daily_with_date",
        "monthly_default",
        "monthly_with_month",
        "yearly_default",
        "yearly_with_year",
    ]
)
@patch('app.scraper.scrape_single_day')
@patch('app.scraper.scrape_entire_month')
@patch('app.scraper.scrape_entire_year')
def test_main_function_calls(mock_scrape_year, mock_scrape_month, mock_scrape_day, command_line_args, expected_function_call):
    """
    測試 main 函式是否能根據不同的命令列參數，正確呼叫對應的 scraper 函式。
    """
    # 執行 main 函式，並傳入模擬的命令列參數
    main(command_line_args)

    # 根據預期的函式呼叫，來進行斷言
    if "scrape_single_day" in expected_function_call:
        mock_scrape_day.assert_called_once()
        mock_scrape_month.assert_not_called()
        mock_scrape_year.assert_not_called()
        # 檢查參數是否正確
        if len(command_line_args) > 1:
            mock_scrape_day.assert_called_with(specific_date=command_line_args[1])
        else:
            mock_scrape_day.assert_called_with()

    elif "scrape_entire_month" in expected_function_call:
        mock_scrape_day.assert_not_called()
        mock_scrape_month.assert_called_once()
        mock_scrape_year.assert_not_called()
        if len(command_line_args) > 1:
            mock_scrape_month.assert_called_with(month_str=command_line_args[1])
        else:
            mock_scrape_month.assert_called_with()

    elif "scrape_entire_year" in expected_function_call:
        mock_scrape_day.assert_not_called()
        mock_scrape_month.assert_not_called()
        mock_scrape_year.assert_called_once()
        if len(command_line_args) > 1:
            mock_scrape_year.assert_called_with(year_str=command_line_args[1])
        else:
            mock_scrape_year.assert_called_with()


@pytest.mark.parametrize(
    "invalid_args, expected_error_msg",
    [
        (["daily", "bad-date-format"], "日期格式不正確"),
        (["monthly", "2025/06"], "月份格式不正確"),
        (["yearly", "25"], "年份格式不正確"),
    ],
    ids=[
        "invalid_date",
        "invalid_month",
        "invalid_year",
    ]
)
def test_main_invalid_arguments(capsys, invalid_args, expected_error_msg):
    """
    測試當傳入無效的參數時，main 函式是否能正確印出錯誤訊息。
    """
    # 執行 main 函式
    main(invalid_args)

    # 使用 capsys fixture 來捕獲印出到終端機的內容
    captured = capsys.readouterr()
    
    # 斷言錯誤訊息是否包含在 stdout 中
    assert expected_error_msg in captured.out
