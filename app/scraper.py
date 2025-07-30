# app/scraper.py

import datetime
import time
import logging
from playwright.sync_api import sync_playwright, expect
import re
from typing import Dict, List, Optional

from app.crud import games, players
from app.utils.state_machine import _update_outs_count, _update_runners_state

from app.config import settings, TEAM_CLUB_CODES
from app.core import fetcher
from app.parsers import box_score, live, schedule, season_stats
from app.db import SessionLocal

logger = logging.getLogger(__name__)


# --- 主要爬蟲邏輯函式 ---


def scrape_and_store_season_stats():
    """抓取並儲存目標球員的球季累積數據。"""
    # TODO: 此函式未來也應重構，以支援多球隊數據的抓取
    club_no = TEAM_CLUB_CODES.get(settings.TARGET_TEAM_NAME)
    if not club_no:
        logger.error(
            f"在設定中找不到球隊 [{settings.TARGET_TEAM_NAME}] 的代碼 (ClubNo)。"
        )
        return

    team_stats_url = f"{settings.TEAM_SCORE_URL}?ClubNo={club_no}"
    logger.info(f"--- 開始抓取球季累積數據，URL: {team_stats_url} ---")

    html_content = fetcher.get_dynamic_page_content(
        team_stats_url, wait_for_selector="div.RecordTable"
    )
    if not html_content:
        logger.error("無法獲取球隊數據頁面內容。")
        return

    season_stats_list = season_stats.parse_season_stats_page(html_content)
    if not season_stats_list:
        logger.info("未解析到任何球員的球季數據。")
        return

    db = SessionLocal()
    try:
        players.store_player_season_stats_and_history(db, season_stats_list)
        db.commit()
    except Exception as e:
        logger.error(f"儲存球季累積數據時發生錯誤，交易已復原: {e}", exc_info=True)
        db.rollback()
    finally:
        if db:
            db.close()

    logger.info("--- 球季累積數據抓取完畢 ---")


def _process_filtered_games(
    games_to_process: List[dict], target_teams: Optional[List[str]] = None
):
    """【修改】處理比賽列表，並可選擇性地只處理指定球隊的比賽。"""
    if not games_to_process:
        return
    logger.info(f"準備處理 {len(games_to_process)} 場比賽...")

    if settings.E2E_TEST_MODE:
        db = SessionLocal()
        try:
            for game_info in games_to_process:
                # 在 E2E 模式下，我們只關心資料是否能成功寫入
                if settings.TARGET_TEAM_NAME not in [
                    game_info.get("home_team"),
                    game_info.get("away_team"),
                ]:
                    continue

                logger.info(
                    f"[E2E] 正在儲存假的比賽資料: {game_info.get('cpbl_game_id')}"
                )
                game_id_in_db = games.store_game_and_get_id(db, game_info)
                if not game_id_in_db:
                    logger.warning(
                        f"[E2E] 無法儲存假的比賽資料: {game_info.get('cpbl_game_id')}"
                    )
                    continue

                fake_player_data = [
                    {
                        "summary": {
                            "player_name": settings.TARGET_PLAYER_NAMES[0],
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
                players.store_player_game_data(db, game_id_in_db, fake_player_data)

            db.commit()
            logger.info("[E2E] 成功提交所有假的比賽資料。")
        except Exception as e:
            logger.error(f"[E2E] 寫入假的比賽資料時發生錯誤: {e}", exc_info=True)
            db.rollback()
        finally:
            if db:
                db.close()
        return

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            slow_mo=300,
            handle_sigint=False,
            handle_sigterm=False,
            handle_sighup=False,
        )
        page = browser.new_page()
        for game_info in games_to_process:
            db = SessionLocal()
            try:
                if game_info.get("status") != "已完成":
                    continue

                # 【修改】如果提供了 target_teams 列表，則只處理相關的比賽
                if target_teams:
                    if (
                        game_info.get("home_team") not in target_teams
                        and game_info.get("away_team") not in target_teams
                    ):
                        continue

                logger.info(f"處理比賽 (CPBL ID: {game_info.get('cpbl_game_id')})...")
                game_id_in_db = games.store_game_and_get_id(db, game_info)
                if not game_id_in_db:
                    continue
                box_score_url = game_info.get("box_score_url")
                if not box_score_url:
                    continue

                page.goto(box_score_url, timeout=settings.PLAYWRIGHT_TIMEOUT)
                page.wait_for_selector(
                    "div.GameBoxDetail", state="visible", timeout=30000
                )
                # 【修改】將 target_teams 參數傳遞給 parser
                all_players_data = box_score.parse_box_score_page(
                    page.content(), target_teams=target_teams
                )
                if not all_players_data:
                    continue

                live_url = box_score_url.replace("/box?", "/box/live?")
                page.goto(
                    live_url, wait_until="load", timeout=settings.PLAYWRIGHT_TIMEOUT
                )
                page.wait_for_selector("div.InningPlaysGroup", timeout=15000)

                full_game_events = []
                inning_buttons = page.locator(
                    "div.InningPlaysGroup div.tabs > ul > li"
                ).all()

                for i, inning_li in enumerate(inning_buttons):
                    inning_num = i + 1
                    logger.info(f"處理第 {inning_num} 局...")
                    inning_li.click()
                    expect(inning_li).to_have_class(re.compile(r"active"))
                    page.wait_for_timeout(250)
                    active_inning_content = page.locator(
                        "div.InningPlaysGroup div.tab_cont.active"
                    )

                    for half_inning_selector in ["section.top", "section.bot"]:
                        half_inning_section = active_inning_content.locator(
                            half_inning_selector
                        )
                        if half_inning_section.count() > 0:
                            expand_buttons = half_inning_section.locator(
                                'a[title="展開打擊紀錄"]'
                            ).all()
                            logger.info(
                                f"處理第 {inning_num} 局 [{half_inning_selector}]，找到 {len(expand_buttons)} 個打席，準備展開..."
                            )
                            for button in expand_buttons:
                                try:
                                    if button.is_visible(timeout=500):
                                        button.click(timeout=500)
                                except Exception:
                                    pass

                    inning_html = active_inning_content.inner_html()
                    parsed_events = live.parse_active_inning_details(
                        inning_html, inning_num
                    )
                    full_game_events.extend(parsed_events)

                all_at_bats_details_enriched = []
                player_pa_counter = {
                    p["summary"]["player_name"]: 0 for p in all_players_data
                }

                inning_state = {}
                for event in full_game_events:
                    inning = event.get("inning")
                    if inning not in inning_state:
                        inning_state[inning] = {
                            "outs": 0,
                            "runners": [None, None, None],
                        }
                    current_outs = inning_state[inning]["outs"]
                    current_runners = inning_state[inning]["runners"]
                    outs_before = current_outs
                    runners_str_list = [
                        base
                        for base, runner in zip(
                            ["一壘", "二壘", "三壘"], current_runners
                        )
                        if runner
                    ]
                    runners_on_base_before = (
                        "、".join(runners_str_list) + "有人"
                        if runners_str_list
                        else "壘上無人"
                    )

                    hitter = event.get("hitter_name")
                    if hitter:
                        if hitter not in player_pa_counter:
                            player_pa_counter[hitter] = 0
                        player_pa_counter[hitter] += 1
                        event["sequence_in_game"] = player_pa_counter[hitter]
                        event["outs_before"] = outs_before
                        event["runners_on_base_before"] = runners_on_base_before
                        all_at_bats_details_enriched.append(event)

                    desc = event.get("description", "")
                    inning_state[inning]["outs"] = _update_outs_count(
                        desc, current_outs
                    )
                    inning_state[inning]["runners"] = _update_runners_state(
                        current_runners, event.get("hitter_name"), desc
                    )
                    if inning_state[inning]["outs"] >= 3:
                        inning_state[inning + 1] = {
                            "outs": 0,
                            "runners": [None, None, None],
                        }

                for player_data in all_players_data:
                    player_name = player_data["summary"]["player_name"]
                    player_live_details = [
                        d
                        for d in all_at_bats_details_enriched
                        if d.get("hitter_name") == player_name
                    ]
                    player_data["at_bats_details"] = []
                    for i, result_short in enumerate(player_data["at_bats_list"]):
                        seq = i + 1
                        merged_at_bat = {
                            "result_short": result_short,
                            "sequence_in_game": seq,
                        }
                        detail_match = next(
                            (
                                d
                                for d in player_live_details
                                if d.get("sequence_in_game") == seq
                            ),
                            None,
                        )
                        if detail_match:
                            merged_at_bat.update(detail_match)
                        player_data["at_bats_details"].append(merged_at_bat)

                players.store_player_game_data(db, game_id_in_db, all_players_data)

                db.commit()
                logger.info(
                    f"成功提交比賽 {game_info.get('cpbl_game_id')} 的所有資料到資料庫。"
                )

            except Exception as e:
                logger.error(
                    f"處理比賽 {game_info.get('cpbl_game_id')} 時發生未知錯誤，將復原此比賽的所有變更: {e}",
                    exc_info=True,
                )
                db.rollback()
            finally:
                if db:
                    db.close()


# --- 主功能函式 ---
def scrape_single_day(
    specific_date: str,  # 仍然需要這個參數用於日誌和檢查
    games_for_day: List[Dict[str, Optional[str]]],  # 新增這個參數，直接傳入當天比賽列表
    update_season_stats: bool = True,
):
    """【功能一】專門抓取並處理指定單日的比賽數據。
    Args:
        specific_date (str): 指定日期，格式 YYYY-MM-DD。用於日誌和日期檢查。
        games_for_day (List[Dict[str, Optional[str]]]): 該日期所有需要處理的比賽資訊列表。
        update_season_stats (bool, optional): 是否執行球季累積數據的抓取。預設為 True。
    """
    logger.info(f"--- 開始執行 [單日模式]，目標日期: {specific_date} ---")

    # 注意：這裡不再檢查 target_date_obj > today 的邏輯，因為這個檢查應該由呼叫方負責。
    # 並且由於現在是直接接收 games_for_day，也不需要再轉換日期格式或檢查無效日期。

    if update_season_stats:
        scrape_and_store_season_stats()

    # 直接使用傳入的 games_for_day 列表
    if not games_for_day:
        logger.info(
            f"--- [單日模式] 目標日期 {specific_date} 沒有找到比賽資料，任務中止 ---"
        )
        return

    _process_filtered_games(games_for_day, target_teams=settings.TARGET_TEAMS)
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
    if not html_content:
        return

    all_month_games = schedule.parse_schedule_page(html_content, target_date_obj.year)

    if target_date_obj.year == today.year and target_date_obj.month == today.month:
        games_to_process = [
            game
            for game in all_month_games
            if datetime.datetime.strptime(game["game_date"], "%Y-%m-%d").date() <= today
        ]
        _process_filtered_games(games_to_process, target_teams=settings.TARGET_TEAMS)
    else:
        _process_filtered_games(all_month_games, target_teams=settings.TARGET_TEAMS)

    logger.info("--- [逐月模式] 執行完畢 ---")


def scrape_entire_year(year_str=None):
    """【功能三】專門抓取並處理指定年份的所有「已完成」比賽數據。"""
    today = datetime.date.today()
    year_to_scrape = int(year_str) if year_str else today.year
    logger.info(f"--- 開始執行 [逐年模式]，目標年份: {year_to_scrape} ---")

    if year_to_scrape > today.year:
        logger.warning(f"目標年份 {year_to_scrape} 是未來年份，任務中止。")
        return

    end_month = today.month if year_to_scrape == today.year else 11
    start_month = 3

    for month in range(start_month, end_month + 1):
        html_content = fetcher.fetch_schedule_page(year_to_scrape, month)
        if html_content:
            all_month_games = schedule.parse_schedule_page(html_content, year_to_scrape)
            logger.info(
                f"月份 {year_to_scrape}-{month:02d} 共解析到 {len(all_month_games)} 場比賽。"
            )
            if all_month_games:
                games_to_process = [
                    game
                    for game in all_month_games
                    if datetime.datetime.strptime(game["game_date"], "%Y-%m-%d").date()
                    <= today
                ]
                _process_filtered_games(
                    games_to_process, target_teams=settings.TARGET_TEAMS
                )
        logger.info(f"處理完 {year_to_scrape}-{month:02d}，稍作等待...")
        time.sleep(settings.FRIENDLY_SCRAPING_DELAY)
    logger.info("--- [逐年模式] 執行完畢 ---")
