# app/api/dashboard.py

from fastapi import APIRouter, Depends

from app.api.dependencies import get_dashboard_service
from app.schemas import DashboardResponse
from app.services.dashboard import DashboardService

router = APIRouter(
    prefix="/api/dashboard",
    tags=["Dashboard"],
)


@router.get(
    "/today",
    response_model=DashboardResponse,
    summary="Get Today's Dashboard",
    description="""
    獲取專為首頁設計的情境驅動儀表板數據。

    - 如果今天有已完成的比賽，將回傳比賽列表。
    - 如果今天沒有已完成的比賽，將回傳下一場比賽的日期以及目標球隊的上一場比賽資訊。
    """,
)
def get_today_dashboard(
    service: DashboardService = Depends(get_dashboard_service),
) -> DashboardResponse:
    """
    根據當日賽況，回傳對應的儀表板數據。
    """
    return service.get_today_dashboard_data()
