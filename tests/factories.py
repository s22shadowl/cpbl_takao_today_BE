# tests/factories.py

import factory
from factory.alchemy import SQLAlchemyModelFactory
import datetime

from app import models


# 建立一個基礎工廠類別，用於設定共用的資料庫 session
class BaseFactory(SQLAlchemyModelFactory):
    class Meta:
        abstract = True
        sqlalchemy_session = None  # 將在 conftest.py 中被設定
        sqlalchemy_session_persistence = "flush"


class GameResultFactory(BaseFactory):
    class Meta:
        model = models.GameResultDB

    cpbl_game_id = factory.Sequence(lambda n: f"TEST_GAME_{n:03}")
    game_date = factory.LazyFunction(datetime.date.today)
    home_team = "主隊"
    away_team = "客隊"


class PlayerGameSummaryFactory(BaseFactory):
    class Meta:
        model = models.PlayerGameSummaryDB

    # 使用 SubFactory 自動建立並關聯一個 GameResultDB 物件
    game = factory.SubFactory(GameResultFactory)
    player_name = factory.Faker("name", locale="zh_TW")
    team_name = "測試隊"
    batting_order = factory.Iterator(["1", "2", "3", "4", "5", "6", "7", "8", "9"])


class AtBatDetailFactory(BaseFactory):
    class Meta:
        model = models.AtBatDetailDB

    # 使用 SubFactory 自動建立並關聯 PlayerGameSummaryDB
    player_summary = factory.SubFactory(PlayerGameSummaryFactory)

    # 透過關聯自動回填 game_id，這是移除 conftest.py 中補丁的關鍵
    game_id = factory.SelfAttribute("player_summary.game.id")

    inning = 1
    sequence_in_game = factory.Sequence(lambda n: n + 1)
    result_short = factory.Iterator(["一安", "二安", "三振", "四壞", "滾地", "飛球"])
    result_description_full = factory.LazyAttribute(
        lambda o: f"詳細描述: {o.result_short}"
    )
