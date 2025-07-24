# app/scraper.py

import datetime
import time
import logging
from playwright.sync_api import sync_playwright, expect
import re

from app.utils.state_machine import _update_outs_count, _update_runners_state

from app.config import settings, TEAM_CLUB_CODES
from app.core import fetcher
from app.core import parser as html_parser
from app import db_actions
from app.db import SessionLocal

logger = logging.getLogger(__name__)


# --- 主要爬蟲邏輯函式 ---


def scrape_and_store_season_stats():
    """抓取並儲存目標球員的球季累積數據。"""
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

    season_stats_list = html_parser.parse_season_stats_page(html_content)
    if not season_stats_list:
        logger.info("未解析到任何目標球員的球季數據。")
        return

    db = SessionLocal()
    try:
        # 【修改】呼叫新的函式，以同時儲存最新數據與歷史紀錄
        db_actions.store_player_season_stats_and_history(db, season_stats_list)
        db.commit()
    except Exception as e:
        logger.error(f"儲存球季累積數據時發生錯誤，交易已復原: {e}", exc_info=True)
        db.rollback()
    finally:
        if db:
            db.close()

    logger.info("--- 球季累積數據抓取完畢 ---")


def _process_filtered_games(games_to_process):
    """【交易管理重構版】處理比賽列表，採用最終正確的「逐局切換、展開、解析」互動邏輯。"""
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
                game_id_in_db = db_actions.store_game_and_get_id(db, game_info)
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
                db_actions.store_player_game_data(db, game_id_in_db, fake_player_data)

            db.commit()
            logger.info("[E2E] 成功提交所有假的比賽資料。")
        except Exception as e:
            logger.error(f"[E2E] 寫入假的比賽資料時發生錯誤: {e}", exc_info=True)
            db.rollback()
        finally:
            if db:
                db.close()
        return  # == E2E 程式碼到此結束 ==

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
                if settings.TARGET_TEAM_NAME not in [
                    game_info.get("home_team"),
                    game_info.get("away_team"),
                ]:
                    continue

                logger.info(
                    f"處理目標球隊比賽 (CPBL ID: {game_info.get('cpbl_game_id')})..."
                )
                game_id_in_db = db_actions.store_game_and_get_id(db, game_info)
                if not game_id_in_db:
                    continue
                box_score_url = game_info.get("box_score_url")
                if not box_score_url:
                    continue

                page.goto(box_score_url, timeout=settings.PLAYWRIGHT_TIMEOUT)
                page.wait_for_selector(
                    "div.GameBoxDetail", state="visible", timeout=30000
                )
                all_players_data = html_parser.parse_box_score_page(page.content())
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
                    is_target_home = settings.TARGET_TEAM_NAME == game_info.get(
                        "home_team"
                    )
                    target_half_inning_selector = (
                        "section.bot" if is_target_home else "section.top"
                    )
                    half_inning_section = active_inning_content.locator(
                        target_half_inning_selector
                    )
                    if half_inning_section.count() > 0:
                        expand_buttons = half_inning_section.locator(
                            'a[title="展開打擊紀錄"]'
                        ).all()
                        logger.info(
                            f"處理第 {inning_num} 局 [{settings.TARGET_TEAM_NAME}]，找到 {len(expand_buttons)} 個打席，準備展開..."
                        )
                        for button in expand_buttons:
                            try:
                                if button.is_visible(timeout=500):
                                    button.click(timeout=500)
                            except Exception:
                                pass

                    inning_html = active_inning_content.inner_html()
                    parsed_events = html_parser.parse_active_inning_details(
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
                    if event.get("hitter_name") in settings.TARGET_PLAYER_NAMES:
                        hitter = event["hitter_name"]
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

                db_actions.store_player_game_data(db, game_id_in_db, all_players_data)

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
def scrape_single_day(specific_date=None):
    """【功能一】專門抓取並處理指定單日的比賽數據。"""
    today = datetime.date.today()
    target_date_str = specific_date if specific_date else today.strftime("%Y-%m-%d")
    logger.info(f"--- 開始執行 [單日模式]，目標日期: {target_date_str} ---")

    try:
        target_date_obj = datetime.datetime.strptime(target_date_str, "%Y-%m-%d").date()
    except ValueError:
        logger.error(f"日期格式錯誤: {target_date_str}")
        return

    if target_date_obj > today and not settings.E2E_TEST_MODE:
        logger.warning(f"目標日期 {target_date_str} 是未來日期，任務中止。")
        return

    scrape_and_store_season_stats()

    html_content = fetcher.fetch_schedule_page(
        target_date_obj.year, target_date_obj.month
    )
    if not html_content:
        logger.info("--- [單日模式] 因無法獲取月賽程而中止 ---")
        return

    all_month_games = html_parser.parse_schedule_page(
        html_content, target_date_obj.year
    )
    games_for_day = [
        game for game in all_month_games if game.get("game_date") == target_date_str
    ]
    _process_filtered_games(games_for_day)
    logger.info("--- [單日模式] 執行完畢 ---")


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

    all_month_games = html_parser.parse_schedule_page(
        html_content, target_date_obj.year
    )

    if target_date_obj.year == today.year and target_date_obj.month == today.month:
        games_to_process = [
            game
            for game in all_month_games
            if datetime.datetime.strptime(game["game_date"], "%Y-%m-%d").date() <= today
        ]
        _process_filtered_games(games_to_process)
    else:
        _process_filtered_games(all_month_games)

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
            all_month_games = html_parser.parse_schedule_page(
                html_content, year_to_scrape
            )
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
                _process_filtered_games(games_to_process)
        logger.info(f"處理完 {year_to_scrape}-{month:02d}，稍作等待...")
        time.sleep(settings.FRIENDLY_SCRAPING_DELAY)
    logger.info("--- [逐年模式] 執行完畢 ---")
