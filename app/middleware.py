# app/middleware.py

from typing import Callable, Awaitable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.utils.request_context import request_id_var, generate_request_id


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # 從請求標頭中獲取 X-Request-ID，如果不存在，則產生一個新的。
        # 這使得在微服務架構中追蹤請求鏈成為可能。
        request_id = request.headers.get("X-Request-ID", generate_request_id())

        # 使用 contextvars 將 request_id 存入當前的上下文中。
        token = request_id_var.set(request_id)

        # 繼續處理請求
        response = await call_next(request)

        # 在回應的標頭中也加入 request_id，方便前端或客戶端追蹤。
        response.headers["X-Request-ID"] = request_id_var.get()

        # 在請求結束時，重設上下文變數。
        request_id_var.reset(token)

        return response
