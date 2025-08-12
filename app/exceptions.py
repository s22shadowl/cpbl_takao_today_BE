# app/exceptions.py

import logging
from enum import Enum
from fastapi import Request, status
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

# --- Scraper Exceptions ---


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
    """

    pass


# --- API Exceptions & Handlers ---


class APIErrorCode(str, Enum):
    """
    集中管理的 API 錯誤碼。
    這份 Enum 本身就是一份給前端工程師的絕佳文件。
    """

    # --- Client-side Errors (4xx) ---
    INVALID_INPUT = "INVALID_INPUT"
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    PLAYER_NOT_FOUND = "PLAYER_NOT_FOUND"
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"

    # --- Server-side Errors (5xx) ---
    INTERNAL_SERVER_ERROR = "INTERNAL_SERVER_ERROR"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    RESULT_BACKEND_NOT_CONFIGURED = "RESULT_BACKEND_NOT_CONFIGURED"


class APIException(Exception):
    """
    自訂 API 例外的基底類別。
    提供預設的 status_code, code, 和 message，並允許在實例化時覆寫。
    """

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    code: APIErrorCode = APIErrorCode.INTERNAL_SERVER_ERROR
    message: str = "An internal server error occurred."

    def __init__(self, message: str | None = None, code: APIErrorCode | None = None):
        if message is not None:
            self.message = message
        if code is not None:
            self.code = code
        # 將最終的 message 傳遞給 Exception 的基底類別
        super().__init__(self.message)


# --- 具體的 API 例外類別 ---


class InvalidInputException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    code = APIErrorCode.INVALID_INPUT
    message = "The provided input is invalid."


class InvalidCredentialsException(APIException):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = APIErrorCode.INVALID_CREDENTIALS
    message = "Invalid authentication credentials."


class PlayerNotFoundException(APIException):
    status_code = status.HTTP_404_NOT_FOUND
    code = APIErrorCode.PLAYER_NOT_FOUND
    message = "The requested player could not be found."


class ResourceNotFoundException(APIException):
    status_code = status.HTTP_404_NOT_FOUND
    code = APIErrorCode.RESOURCE_NOT_FOUND
    message = "The requested resource could not be found."


class ServiceUnavailableException(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = APIErrorCode.SERVICE_UNAVAILABLE
    message = "The service is temporarily unavailable."


class ResultBackendNotConfiguredException(APIException):
    status_code = status.HTTP_501_NOT_IMPLEMENTED
    code = APIErrorCode.RESULT_BACKEND_NOT_CONFIGURED
    message = "Result backend is not configured for the broker."


# --- 全域例外處理器 ---


async def api_exception_handler(request: Request, exc: APIException):
    """
    攔截所有可預期的 APIException，記錄警告日誌，並回傳標準化的 JSON 錯誤回應。
    """
    logger.warning(
        f"API Exception Handled: "
        f"Status={exc.status_code}, "
        f"Code='{exc.code.value}', "
        f"Path='{request.url.path}', "
        f"Detail='{exc.message}'"
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code.value, "message": exc.message},
    )


async def unhandled_exception_handler(request: Request, exc: Exception):
    """
    攔截所有未預期的錯誤，記錄包含 Traceback 的錯誤日誌，並回傳通用的 500 錯誤。
    這可以防止將內部實作細節 (如 Python Traceback) 洩漏給客戶端。
    """
    logger.error(
        f"Unhandled Exception: {exc}",
        exc_info=True,  # 包含完整的 Traceback
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "code": APIErrorCode.INTERNAL_SERVER_ERROR.value,
            "message": "An unexpected error occurred on the server.",
        },
    )
