# tests/parsers/test_schedule.py
import pytest
from pathlib import Path
from app.parsers import schedule

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"

# --- Fixtures ---


@pytest.fixture
def schedule_html_content():
    schedule_file = FIXTURES_DIR / "schedule_page.html"
    if not schedule_file.exists():
        pytest.skip("測試素材 schedule_page.html 不存在，跳過相關測試。")
    return schedule_file.read_text(encoding="utf-8")


def test_parse_schedule_page(schedule_html_content):
    result = schedule.parse_schedule_page(schedule_html_content, year=2025)
    assert isinstance(result, list)
    assert len(result) > 0
