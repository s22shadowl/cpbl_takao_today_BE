# app/utils/request_context.py

import uuid
from contextvars import ContextVar
from typing import Optional

# 定義一個上下文變數，專門用來存放當前請求的 request_id。
# 它的預設值是 None。
request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)


def generate_request_id() -> str:
    """產生一個新的 UUID 作為 request_id。"""
    return str(uuid.uuid4())
