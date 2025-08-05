# app/exceptions.py


class ScraperError(Exception):
    """
    所有爬蟲相關錯誤的基礎例外類別。
    """

    pass


class RetryableScraperError(ScraperError):
    """
    代表一個可重試的錯誤。

    這種類型的錯誤通常是暫時性的，例如：
    - 網路連線逾時
    - DNS 解析失敗
    - 遠端伺服器回傳 HTTP 5xx 錯誤 (e.g., 502, 503, 504)
    """

    pass


class FatalScraperError(ScraperError):
    """
    代表一個不可重試的、致命的錯誤。

    這種類型的錯誤通常表示爬蟲的底層邏輯已失效，需要開發者介入修復，
    不斷重試是沒有意義的。例如：
    - 目標網站 HTML 結構變更，導致解析器找不到關鍵元素。
    - API 端點的 URL 變更，導致持續收到 HTTP 404 錯誤。
    - 應用程式的內部邏輯錯誤 (e.g., TypeError, ValueError)。
    """

    pass


class GameNotFinalError(ScraperError):
    """
    代表一場比賽因其狀態而非最終狀態，因此應跳過本次爬取。

    這不是一個需要重試的錯誤，而是一個業務邏輯上的信號，
    表示應等待比賽結束後再進行處理。

    可能的情境包括：
    - 比賽尚未開始 (e.g., 狀態為 '未開賽')
    - 比賽正在進行中 (e.g., 狀態為 '比賽中')
    - 比賽因故暫停 (e.g., 狀態為 '暫停中')
    - 比賽延期舉行 (e.g., 狀態為 '延賽')
    - 比賽被裁定為保留比賽 (e.g., 狀態為 '保留比賽')
    """

    pass
