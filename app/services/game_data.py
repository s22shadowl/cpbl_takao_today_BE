# app/services/game_data.py

import datetime
import time
import logging
from playwright.sync_api import expect
from typing import Dict, List, Optional

from app.crud import games, players
from app.models import AtBatResultType
from app.utils.state_machine import _update_outs_count, _update_runners_state
from app.utils.parsing_helpers import is_formal_pa, map_result_short_to_type

from app.config import settings
from app.core import fetcher
from app.parsers import box_score, live, schedule, season_stats
from app.db import SessionLocal
from app.exceptions import ScraperError
from app.browser import get_page
from app.services import player as player_service


logger = logging.getLogger(__name__)


# --- 主要爬蟲邏輯函式 ---


def scrape_and_store_season_stats(update_career_stats_for_all: bool = False):
    """
    抓取並儲存目標球隊的球季累積數據，並觸發生涯數據的更新。

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
    logger.info(f"--- 開始抓取球季累積數據，URL: {team_stats_url} ---")

    html_content = fetcher.get_dynamic_page_content(
        team_stats_url, wait_for_selector="div.RecordTable"
    )
    season_stats_list = season_stats.parse_season_stats_page(html_content)
    if not season_stats_list:
        logger.info("未解析到任何球員的球季數據。")
        return

    db = SessionLocal()
    try:
        players.store_player_season_stats_and_history(db, season_stats_list)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        if db:
            db.close()

    logger.info("--- 球季累積數據抓取完畢 ---")

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
        logger.info("沒有需要更新生涯數據的球員，任務結束。")
        return

    logger.info(
        f"--- 開始為 {len(players_to_update_career_stats)} 位球員觸發生涯數據更新 ---"
    )
    for player_stats in players_to_update_career_stats:
        player_name = player_stats.get("player_name")
        player_url = player_stats.get("player_url")
        if player_name and player_url:
            try:
                player_service.scrape_and_store_player_career_stats(
                    player_name=player_name, player_url=player_url
                )
                time.sleep(settings.FRIENDLY_SCRAPING_DELAY)
            except Exception as e:
                logger.error(
                    f"在為球員 [{player_name}] 更新生涯數據時失敗: {e}", exc_info=True
                )
    logger.info("--- 所有球員生涯數據更新流程已完成 ---")


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

                game_date = datetime.datetime.strptime(
                    game_info["game_date"], "%Y-%m-%d"
                ).date()
                games.delete_game_if_exists(
                    db, game_info.get("cpbl_game_id"), game_date
                )
                game_id_in_db = games.create_game_and_get_id(db, game_info)

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

    with get_page(headless=False) as page:
        for game_info in games_to_process:
            db = SessionLocal()
            try:
                if target_teams and not any(
                    team in target_teams
                    for team in [game_info.get("home_team"), game_info.get("away_team")]
                ):
                    continue

                logger.info(f"處理比賽 (CPBL ID: {game_info.get('cpbl_game_id')})...")

                game_date = datetime.datetime.strptime(
                    game_info["game_date"], "%Y-%m-%d"
                ).date()
                games.delete_game_if_exists(
                    db, game_info.get("cpbl_game_id"), game_date
                )
                game_id_in_db = games.create_game_and_get_id(db, game_info)

                if not game_id_in_db:
                    continue

                box_score_url = game_info.get("box_score_url")
                if not box_score_url:
                    continue

                page.goto(box_score_url, timeout=settings.PLAYWRIGHT_TIMEOUT)
                page.wait_for_selector(
                    "div.GameBoxDetail",
                    state="visible",
                    timeout=settings.PLAYWRIGHT_TIMEOUT,
                )
                all_players_data = box_score.parse_box_score_page(
                    page.content(), target_teams=target_teams
                )
                if not all_players_data:
                    continue

                live_url = box_score_url.replace("/box?", "/box/live?")
                page.goto(
                    live_url, wait_until="load", timeout=settings.PLAYWRIGHT_TIMEOUT
                )
                page.wait_for_selector(
                    "div.InningPlaysGroup", timeout=settings.PLAYWRIGHT_TIMEOUT
                )

                logger.info("注入 CSS 以隱藏所有 iframe...")
                try:
                    page.add_style_tag(content="iframe { display: none !important; }")
                    logger.debug("CSS 注入成功。")
                except Exception as e:
                    logger.error(f"注入 CSS 時發生錯誤: {e}")

                full_game_events = []
                inning_buttons = page.locator(
                    "div.InningPlaysGroup div.tabs > ul > li"
                ).all()

                for i, inning_li in enumerate(inning_buttons):
                    inning_num = i + 1
                    logger.info(f"處理第 {inning_num} 局...")

                    inning_li.click()

                    try:
                        active_inning_content = page.locator(
                            "div.InningPlaysGroup div.tab_cont.active"
                        )
                        expect(active_inning_content).to_be_visible(timeout=5000)
                        logger.debug(f"第 {inning_num} 局內容已可見。")
                    except Exception as e:
                        logger.error(
                            f"等待第 {inning_num} 局內容可見時超時或失敗: {e}，將跳過此局。"
                        )
                        continue

                    for half_inning_selector in ["section.top", "section.bot"]:
                        batting_team = (
                            game_info["away_team"]
                            if half_inning_selector == "section.top"
                            else game_info["home_team"]
                        )

                        half_inning_section = active_inning_content.locator(
                            half_inning_selector
                        )

                        if half_inning_section.count() > 0:
                            # 【FIX】修正邏輯：如果 target_teams 未指定，則處理所有隊伍；否則只處理目標隊伍。
                            if not target_teams or batting_team in target_teams:
                                event_containers = half_inning_section.locator(
                                    "div.item.play"
                                )
                                container_count = event_containers.count()

                                logger.info(
                                    f"處理第 {inning_num} 局 [{half_inning_selector}]，找到 {container_count} 個打席容器，準備展開..."
                                )

                                for i in range(container_count):
                                    item_container = event_containers.nth(i)

                                    bell_button = item_container.locator(
                                        "div.no-pitch-action-remind"
                                    )
                                    event_button = item_container.locator(
                                        "div.batter_event"
                                    )
                                    event_anchor = event_button.locator("a")

                                    target_to_click = None
                                    anchor_text = (
                                        event_anchor.text_content(timeout=500) or ""
                                    ).strip()

                                    if anchor_text:
                                        target_to_click = event_button
                                    elif bell_button.count() > 0:
                                        target_to_click = bell_button

                                    if not target_to_click:
                                        continue

                                    for attempt in range(2):
                                        try:
                                            target_to_click.scroll_into_view_if_needed()
                                            page.wait_for_timeout(100)
                                            target_to_click.hover(
                                                force=True, timeout=3000
                                            )
                                            page.wait_for_timeout(100)
                                            target_to_click.click(
                                                force=True, timeout=2000
                                            )
                                            break
                                        except Exception as e:
                                            logger.warning(
                                                f"點擊第 {i + 1} 個按鈕時失敗 (嘗試 {attempt + 1}): {e}",
                                                exc_info=False,
                                            )
                                            if attempt == 1:
                                                logger.error(
                                                    f"重試多次後，點擊第 {i + 1} 個按鈕仍然失敗。"
                                                )

                                # 【最終修正】將解析邏輯移入半局過濾區塊內
                                inning_html = half_inning_section.inner_html()
                                parsed_events = live.parse_active_inning_details(
                                    inning_html, inning_num
                                )
                                full_game_events.extend(parsed_events)
                            else:
                                logger.info(
                                    f"跳過第 {inning_num} 局 [{half_inning_selector}]，進攻方 ({batting_team}) 非目標球隊。"
                                )

                player_pa_counter = {
                    p["summary"]["player_name"]: 0 for p in all_players_data
                }

                all_at_bats_details_enriched = []
                inning_state = {}
                for i, event in enumerate(full_game_events):
                    inning = event.get("inning")

                    if inning not in inning_state:
                        inning_state[inning] = {
                            "outs": 0,
                            "runners": [None, None, None],
                        }

                    if inning_state[inning]["outs"] >= 3:
                        inning_state[inning]["outs"] = 0
                        inning_state[inning]["runners"] = [None, None, None]

                    current_outs = inning_state[inning]["outs"]
                    current_runners = inning_state[inning]["runners"]

                    event["outs_before"] = current_outs
                    runners_str_list = [
                        base
                        for base, runner in zip(
                            ["一壘", "二壘", "三壘"], current_runners
                        )
                        if runner
                    ]
                    event["runners_on_base_before"] = (
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

                    all_at_bats_details_enriched.append(event)

                    desc = event.get("description", "")

                    new_outs = _update_outs_count(desc, current_outs)
                    new_runners = _update_runners_state(current_runners, hitter, desc)

                    inning_state[inning]["outs"] = new_outs
                    inning_state[inning]["runners"] = new_runners

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

                                # [修改] 以 result_short 為主的 result_type 決定邏輯
                                mapped_type = map_result_short_to_type(
                                    result_short_from_box
                                )
                                if mapped_type:
                                    live_event["result_type"] = mapped_type
                                # 如果映射失敗，則保留 parser 的 fallback 結果

                            except StopIteration:
                                logger.warning(
                                    f"資料不一致：球員 [{hitter_name}] 的 Live Text 事件比 Box Score 打席數多。"
                                )
                                live_event["result_short"] = "未知"
                        else:
                            live_event["result_short"] = "無"
                            # [修改] 當打席未完成時，將 result_type 設為 INCOMPLETE_PA
                            live_event["result_type"] = AtBatResultType.INCOMPLETE_PA

                        player_data["at_bats_details"].append(live_event)

                final_player_data_list = list(player_data_map.values())
                for p_data in final_player_data_list:
                    if "box_score_iterator" in p_data:
                        del p_data["box_score_iterator"]

                players.store_player_game_data(
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
