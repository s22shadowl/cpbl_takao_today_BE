# app/services/game_data.py

import datetime
import time
import logging
from typing import Dict, List, Optional

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from app.models import AtBatResultType
from app.utils.parsing_helpers import is_formal_pa, map_result_short_to_type

from app.config import settings
from app.core import fetcher
from app.parsers import box_score, live, schedule, season_stats
from app.db import SessionLocal
from app.exceptions import ScraperError
from app.browser import get_page
from app.services import player as player_service, data_persistence
from app.services.browser_operator import BrowserOperator
from app.services.game_state_machine import GameStateMachine


logger = logging.getLogger(__name__)


# --- [T31-3 新增] 獨立的爬蟲邏輯函式 ---


def _scrape_and_store_batting_stats(
    page: Page, team_stats_url: str, update_career_stats_for_all: bool = False
):
    """抓取並儲存球季打擊數據，並觸發生涯數據更新。"""
    logger.info("--- (1/2) 開始抓取球季累積打擊數據 ---")
    try:
        page.goto(team_stats_url, wait_until="networkidle")
        page.wait_for_selector("div.RecordTable", timeout=15000)
        html_content = page.content()
    except PlaywrightTimeoutError:
        logger.error("等待打擊數據表格時超時，無法抓取打擊數據。")
        return

    season_stats_list = season_stats.parse_season_batting_stats_page(html_content)
    if not season_stats_list:
        logger.info("未解析到任何球員的球季打擊數據。")
        return

    db = SessionLocal()
    try:
        from app.crud import players

        players.store_player_season_stats_and_history(db, season_stats_list)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        if db:
            db.close()

    logger.info("--- 球季累積打擊數據抓取完畢 ---")

    # --- 後續的生涯數據更新邏輯 ---
    players_to_update_career_stats = []
    if update_career_stats_for_all:
        logger.info("模式：更新所有球員的生涯數據。")
        players_to_update_career_stats = season_stats_list
    else:
        logger.info(f"模式：僅更新目標球員 {settings.TARGET_PLAYER_NAMES} 的生涯數據。")
        players_to_update_career_stats = [
            p
            for p in season_stats_list
            if p["player_name"] in settings.TARGET_PLAYER_NAMES
        ]

    if not players_to_update_career_stats:
        logger.info("沒有需要更新生涯數據的球員。")
        return

    logger.info(
        f"--- 開始為 {len(players_to_update_career_stats)} 位球員觸發生涯數據更新 ---"
    )
    for player_stats in players_to_update_career_stats:
        player_name = player_stats.get("player_name")
        player_url = player_stats.get("player_url")
        if player_name and player_url:
            try:
                # [修正] 傳遞已存在的 page 物件
                player_service.scrape_and_store_player_career_stats(
                    page=page, player_name=player_name, player_url=player_url
                )
                time.sleep(settings.FRIENDLY_SCRAPING_DELAY)
            except Exception as e:
                logger.error(
                    f"在為球員 [{player_name}] 更新生涯數據時失敗: {e}", exc_info=True
                )
    logger.info("--- 所有球員生涯數據更新流程已完成 ---")


def _scrape_and_store_fielding_stats(
    page: Page,
    team_stats_url: str,
):
    """在同一個瀏覽器頁面中，接續抓取並儲存球季守備數據。"""
    logger.info("--- (2/2) 開始抓取球季累積守備數據--- ")
    try:
        # 1. 選擇「守備成績」
        page.goto(team_stats_url, wait_until="networkidle")
        page.wait_for_selector("div.RecordTable", timeout=15000)
        page.select_option("#Position", "03")
        # 2. 點擊「查詢」按鈕
        page.click('input[value="查詢"]')

        # 3. [修正] 直接等待預期結果出現，而不是等待不穩定的載入動畫。
        #    當守備數據表格載入後，其標頭 "刺殺" 必定會出現。
        page.wait_for_selector('th:has-text("守備位置")', timeout=15000)

        html_content = page.content()
    except PlaywrightTimeoutError as e:
        logger.error(
            f"等待守備數據表格時超時或互動失敗，無法抓取守備數據。{e}", exc_info=True
        )
        return
    except Exception as e:
        logger.error(f"抓取守備數據時發生未預期的瀏覽器錯誤: {e}", exc_info=True)
        return

    fielding_stats_list = season_stats.parse_season_fielding_stats_page(html_content)
    if not fielding_stats_list:
        logger.info("未解析到任何球員的球季守備數據。")
        return

    db = SessionLocal()
    try:
        from app.crud import players

        players.store_player_fielding_stats(db, fielding_stats_list)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        if db:
            db.close()

    logger.info("--- 球季累積守備數據抓取完畢 ---")


# --- [T31-3 重構] 主要爬蟲協調函式 ---


def scrape_and_store_season_stats(update_career_stats_for_all: bool = False):
    """
    [協調函式] 抓取並儲存目標球隊的球季累積數據 (包含打擊與守備)。

    Args:
        update_career_stats_for_all (bool):
            - True: 更新球隊頁面上所有球員的生涯數據。
            - False (預設): 僅更新 settings.TARGET_PLAYER_NAMES 中指定的球員。
    """
    club_no = settings.TEAM_CLUB_CODES.get(settings.TARGET_TEAM_NAME)
    if not club_no:
        logger.error(
            f"在設定中找不到球隊 [{settings.TARGET_TEAM_NAME}] 的代碼 (ClubNo)。"
        )
        return

    team_stats_url = f"{settings.TEAM_SCORE_URL}?ClubNo={club_no}"
    logger.info(f"--- 開始抓取球季累積數據 (打擊與守備)，URL: {team_stats_url} ---")

    try:
        with get_page(headless=False) as page:
            # 任務一：抓取打擊數據
            _scrape_and_store_batting_stats(
                page, team_stats_url, update_career_stats_for_all
            )

            # 任務二：在同一個 page 中，接續抓取守備數據
            _scrape_and_store_fielding_stats(page, team_stats_url)

    except Exception as e:
        logger.error(f"執行球季數據抓取主流程時發生嚴重錯誤: {e}", exc_info=True)
        # 確保在發生不可預期的錯誤時，也能記錄下來

    logger.info("--- 球季數據 (打擊與守備) 完整抓取流程結束 ---")


def _process_filtered_games(
    games_to_process: List[dict], target_teams: Optional[List[str]] = None
):
    """處理比賽列表，並可選擇性地只處理指定球隊的比賽。"""
    if not games_to_process:
        return
    logger.info(f"準備處理 {len(games_to_process)} 場比賽...")

    if settings.E2E_TEST_MODE:
        db = SessionLocal()
        try:
            for game_info in games_to_process:
                if settings.TARGET_TEAM_NAME not in [
                    game_info.get("home_team"),
                    game_info.get("away_team"),
                ]:
                    continue

                logger.info(
                    f"[E2E] 正在儲存假的比賽資料: {game_info.get('cpbl_game_id')}"
                )

                game_info["game_date_obj"] = datetime.datetime.strptime(
                    game_info["game_date"], "%Y-%m-%d"
                ).date()

                game_id_in_db = data_persistence.prepare_game_storage(db, game_info)

                if not game_id_in_db:
                    logger.warning(
                        f"[E2E] 無法儲存假的比賽資料: {game_info.get('cpbl_game_id')}"
                    )
                    continue

                fake_player_data = [
                    {
                        "summary": {
                            "player_name": settings.get_target_players_as_list()[0],
                            "team_name": settings.TARGET_TEAM_NAME,
                            "batting_order": "1",
                            "position": "CF",
                        },
                        "at_bats_details": [
                            {
                                "inning": 1,
                                "result_short": "安打",
                                "description": "一壘安打",
                            }
                        ],
                    }
                ]
                data_persistence.commit_player_game_data(
                    db, game_id_in_db, fake_player_data
                )

            db.commit()
            logger.info("[E2E] 成功提交所有假的比賽資料。")
        except Exception as e:
            logger.error(f"[E2E] 寫入假的比賽資料時發生錯誤: {e}", exc_info=True)
            db.rollback()
        finally:
            if db:
                db.close()
        return

    with get_page(headless=False) as page:
        browser_operator = BrowserOperator(page)

        for game_info in games_to_process:
            db = SessionLocal()
            try:
                if target_teams and not any(
                    team in target_teams
                    for team in [game_info.get("home_team"), game_info.get("away_team")]
                ):
                    continue

                logger.info(f"處理比賽 (CPBL ID: {game_info.get('cpbl_game_id')})...")

                # 預先處理日期物件，供後續使用
                game_info["game_date_obj"] = datetime.datetime.strptime(
                    game_info["game_date"], "%Y-%m-%d"
                ).date()

                # [重構] 透過 DataPersistence 服務處理資料庫準備
                game_id_in_db = data_persistence.prepare_game_storage(db, game_info)
                if not game_id_in_db:
                    continue

                box_score_url = game_info.get("box_score_url")
                if not box_score_url:
                    continue

                box_score_html = browser_operator.navigate_and_get_box_score_content(
                    box_score_url
                )
                all_players_data = box_score.parse_box_score_page(
                    box_score_html, target_teams=target_teams
                )
                if not all_players_data:
                    continue

                live_url = box_score_url.replace("/box?", "/box/live?")
                all_half_innings_html = browser_operator.extract_live_events_html(
                    live_url
                )

                full_game_events = []
                for (
                    inning_html,
                    inning_num,
                    half_inning_selector,
                ) in all_half_innings_html:
                    batting_team = (
                        game_info["away_team"]
                        if half_inning_selector == "section.top"
                        else game_info["home_team"]
                    )

                    if not target_teams or batting_team in target_teams:
                        parsed_events = live.parse_active_inning_details(
                            inning_html, inning_num
                        )
                        full_game_events.extend(parsed_events)

                state_machine = GameStateMachine(all_players_data)
                all_at_bats_details_enriched = state_machine.enrich_events_with_state(
                    full_game_events
                )

                player_data_map = {
                    p["summary"]["player_name"]: p for p in all_players_data
                }

                for player_name, p_data in player_data_map.items():
                    p_data["at_bats_details"] = []
                    p_data["box_score_iterator"] = iter(p_data.get("at_bats_list", []))

                for live_event in all_at_bats_details_enriched:
                    hitter_name = live_event.get("hitter_name")

                    if hitter_name and hitter_name in player_data_map:
                        player_data = player_data_map[hitter_name]
                        description = live_event.get("description", "")

                        if is_formal_pa(description):
                            try:
                                result_short_from_box = next(
                                    player_data["box_score_iterator"]
                                )
                                live_event["result_short"] = result_short_from_box

                                mapped_type = map_result_short_to_type(
                                    result_short_from_box
                                )
                                if mapped_type:
                                    live_event["result_type"] = mapped_type

                            except StopIteration:
                                logger.warning(
                                    f"資料不一致：球員 [{hitter_name}] 的 Live Text 事件比 Box Score 打席數多。"
                                )
                                live_event["result_short"] = "未知"
                        else:
                            live_event["result_short"] = "無"
                            live_event["result_type"] = AtBatResultType.INCOMPLETE_PA

                        player_data["at_bats_details"].append(live_event)

                final_player_data_list = list(player_data_map.values())
                for p_data in final_player_data_list:
                    if "box_score_iterator" in p_data:
                        del p_data["box_score_iterator"]

                # [重構] 透過 DataPersistence 服務儲存最終資料
                data_persistence.commit_player_game_data(
                    db, game_id_in_db, final_player_data_list
                )
                db.commit()
                logger.info(
                    f"成功提交比賽 {game_info.get('cpbl_game_id')} 的所有資料到資料庫。"
                )

            except Exception:
                logger.error(
                    f"處理比賽 {game_info.get('cpbl_game_id')} 時發生錯誤，將復原此比賽的所有變更。",
                    exc_info=True,
                )
                db.rollback()
                raise
            finally:
                if db:
                    db.close()


# --- 主功能函式 ---
def scrape_single_day(
    specific_date: str,
    games_for_day: List[Dict[str, Optional[str]]],
    update_season_stats: bool = True,
):
    """【功能一】專門抓取並處理指定單日的比賽數據。"""
    logger.info(f"--- 開始執行 [單日模式]，目標日期: {specific_date} ---")

    if update_season_stats:
        scrape_and_store_season_stats()

    if not games_for_day:
        logger.info(
            f"--- [單日模式] 目標日期 {specific_date} 沒有找到比賽資料，任務中止 ---"
        )
        return

    _process_filtered_games(
        games_for_day, target_teams=settings.get_target_teams_as_list()
    )
    logger.info(f"--- [單日模式] 日期 {specific_date} 執行完畢 ---")


def scrape_entire_month(month_str=None):
    """【功能二】專門抓取並處理指定月份的所有「已完成」比賽數據。"""
    today = datetime.date.today()
    target_date_obj = (
        datetime.datetime.strptime(month_str, "%Y-%m").date().replace(day=1)
        if month_str
        else today.replace(day=1)
    )
    logger.info(
        f"--- 開始執行 [逐月模式]，目標月份: {target_date_obj.strftime('%Y-%m')} ---"
    )

    if target_date_obj.year > today.year or (
        target_date_obj.year == today.year and target_date_obj.month > today.month
    ):
        logger.warning(
            f"目標月份 {target_date_obj.strftime('%Y-%m')} 是未來月份，任務中止。"
        )
        return

    html_content = fetcher.fetch_schedule_page(
        target_date_obj.year, target_date_obj.month
    )
    all_month_games = schedule.parse_schedule_page(html_content, target_date_obj.year)

    games_to_process = [
        game
        for game in all_month_games
        if datetime.datetime.strptime(game["game_date"], "%Y-%m-%d").date() <= today
    ]
    _process_filtered_games(
        games_to_process, target_teams=settings.get_target_teams_as_list()
    )

    logger.info("--- [逐月模式] 執行完畢 ---")


def scrape_entire_year(year_str=None):
    """【功能三】專門抓取並處理指定年份的所有「已完成」比賽數據。"""
    today = datetime.date.today()
    year_to_scrape = int(year_str) if year_str else today.year
    logger.info(f"--- 開始執行 [逐年模式]，目標年份: {year_to_scrape} ---")

    if year_to_scrape > today.year:
        logger.warning(f"目標年份 {year_to_scrape} 是未來年份，任務中止。")
        return

    end_month = (
        today.month if year_to_scrape == today.year else settings.CPBL_SEASON_END_MONTH
    )
    start_month = settings.CPBL_SEASON_START_MONTH

    for month in range(start_month, end_month + 1):
        try:
            html_content = fetcher.fetch_schedule_page(year_to_scrape, month)
            all_month_games = schedule.parse_schedule_page(html_content, year_to_scrape)
            logger.info(
                f"月份 {year_to_scrape}-{month:02d} 共解析到 {len(all_month_games)} 場比賽。"
            )

            games_to_process = [
                game
                for game in all_month_games
                if datetime.datetime.strptime(game["game_date"], "%Y-%m-%d").date()
                <= today
            ]
            _process_filtered_games(
                games_to_process, target_teams=settings.get_target_teams_as_list()
            )
        except ScraperError:
            logger.error(
                f"處理月份 {year_to_scrape}-{month:02d} 時發生爬蟲錯誤，已跳過此月份。",
                exc_info=True,
            )

        logger.info(f"處理完 {year_to_scrape}-{month:02d}，稍作等待...")
        time.sleep(settings.FRIENDLY_SCRAPING_DELAY)
    logger.info("--- [逐年模式] 執行完畢 ---")
