# app/api/system.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.db import get_db

router = APIRouter(
    prefix="/api/system",
    tags=["System"],
    responses={404: {"description": "Not found"}},
)


@router.get("/health", status_code=status.HTTP_200_OK)
def health_check(db: Session = Depends(get_db)):
    """
    執行健康檢查。

    這個端點會嘗試連接資料庫並執行一個簡單的查詢，以確認服務本身
    及其關鍵依賴（資料庫）是否都正常運作。

    - **成功**: 回傳 HTTP 200 OK，表示服務健康。
    - **失敗**: 回傳 HTTP 503 Service Unavailable，表示服務的依賴項（資料庫）出現問題。
    """
    try:
        # 執行一個最簡單、成本最低的查詢來驗證資料庫連線
        db.execute(text("SELECT 1"))
        return {"status": "ok", "database": "ok"}
    except Exception as e:
        # 如果資料庫連線失敗，拋出 503 錯誤
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database connection error: {e}",
        )
