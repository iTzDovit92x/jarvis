"""
Tests for Jarvis's Tier 1 router and memory.

Run them with:   .venv\\Scripts\\python.exe -m pytest
Each test gets its own empty vault in a temporary folder, so your real one is never touched.
"""

import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
import memory   # noqa: E402
import router   # noqa: E402


@pytest.fixture(autouse=True)
def vault(tmp_path):
    memory.use_vault(tmp_path / "vault")
    memory.setup()
    yield tmp_path / "vault"


# ---------------------------------------------------------------------------
# Spoken numbers
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("said, minutes", [
    ("log 45 minutes", 45),
    ("log forty five minutes", 45),
    ("log forty-five minutes", 45),
    ("i did an hour of python", 60),
    ("i studied for half an hour", 30),
    ("log an hour and a half", 90),
    ("log 2 hours and 15 minutes", 135),
    ("log 1.5 hours", 90),
    ("log two hours", 120),
    ("what's up", None),
])
def test_parse_minutes(said, minutes):
    assert router.parse_minutes(said) == minutes


# ---------------------------------------------------------------------------
# Study logging, streak and hours
# ---------------------------------------------------------------------------
def test_log_study_by_voice():
    reply = router.route("Jarvis, log 45 minutes of Python.")
    assert reply.startswith("Logged 45 minutes")
    assert memory.minutes_by_day()[date.today()] == 45


def test_log_study_with_topic():
    router.route("log an hour on list comprehensions")
    assert "list comprehensions" in memory.STUDY_LOG.read_text()


def test_streak_counts_consecutive_days():
    today = date(2026, 11, 5)
    for days_ago in (0, 1, 2):
        memory.log_study(30, when=datetime.combine(today - timedelta(days=days_ago), datetime.min.time()))
    memory.log_study(30, when=datetime.combine(today - timedelta(days=5), datetime.min.time()))  # gap
    assert memory.streak(today) == 3


def test_streak_survives_until_today_is_over():
    today = date(2026, 11, 5)
    memory.log_study(30, when=datetime.combine(today - timedelta(days=1), datetime.min.time()))
    assert memory.streak(today) == 1


def test_week_hours_only_counts_since_monday():
    wednesday = date(2026, 11, 4)
    memory.log_study(60, when=datetime(2026, 11, 2, 19, 0))   # Monday: counts
    memory.log_study(90, when=datetime(2026, 11, 4, 19, 0))   # Wednesday: counts
    memory.log_study(120, when=datetime(2026, 11, 1, 19, 0))  # last Sunday: doesn't
    assert memory.week_hours(wednesday) == 2.5


def test_ask_streak_and_week():
    assert "No streak yet" in router.route("what's my streak?")
    router.route("log 30 minutes of python")
    assert "1-day streak" in router.route("What's my streak")
    assert "0.5 hours this week" in router.route("how many hours have I studied this week")


# ---------------------------------------------------------------------------
# Shift
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("said, expected", [
    ("I'm on backshift this week", "backshift"),
    ("i'm on back shift this week", "backshift"),
    ("I'm on the night shift this week", "nightshift"),
    ("im on days this week", "dayshift"),
    ("I'm off this week", "off"),
])
def test_set_shift(said, expected):
    assert router.route(said)
    assert memory.get_shift() == expected


def test_next_week_shift_is_not_this_week():
    router.route("I'm on nights next week")
    assert memory.get_shift() is None
    assert memory.get_shift(date.today() + timedelta(days=7)) == "nightshift"


def test_ask_shift():
    assert "haven't told me" in router.route("what shift am I on")
    router.route("I'm on backshift this week")
    assert router.route("what shift am I on") == "You're on backshift this week."


# ---------------------------------------------------------------------------
# Directives and roadmap
# ---------------------------------------------------------------------------
def test_add_and_tick_task():
    assert router.route("add a task to update my CV") == "Added to your list: Update my CV."
    assert "Update my CV" in router.route("what's on my list")
    assert router.route("tick off update my cv").startswith("Ticked off")
    assert all(d["done"] for d in memory.directives() if "cv" in d["text"].lower())


def test_tick_off_fuzzy_match():
    assert router.route("tick off github") == "Ticked off: Push Jarvis to GitHub."


def test_finished_topic():
    reply = router.route("I've finished variables")
    assert "Variables, types and f-strings is done" in reply
    assert memory.roadmap()["current"] == "Lists, dictionaries and loops"


def test_next_topic():
    router.route("next topic")
    assert memory.roadmap()["done"] == 1


def test_roadmap_question():
    assert router.route("what's next on my roadmap").startswith("You're on Variables")


def test_toggle_from_hud_keeps_other_lines(vault):
    memory.toggle_directive(0)
    text = memory.DIRECTIVES.read_text()
    assert text.startswith("# Directives")
    assert "- [x] Push Jarvis to GitHub" in text


# ---------------------------------------------------------------------------
# Jobs and time
# ---------------------------------------------------------------------------
def test_log_application():
    reply = router.route("I applied for a junior developer role at Acme")
    assert "1 application" in reply
    assert "applied | Acme | junior developer" in memory.JOBS.read_text()
    assert router.route("how many applications") == "1 application sent, 0 interviews and 0 offers."


def test_time():
    assert router.route("what time is it").startswith("It's ")


# ---------------------------------------------------------------------------
# Things that must go to Claude, not get caught by a rule
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("said", [
    "What's a Python decorator?",
    "I did an hour on list comprehensions",
    "How many hours is a typical software engineer shift?",
    "I spent 20 minutes debugging this error, what's wrong with it",
    "what time is it in Tokyo",
    "What's next for AI in 2027?",
    "how do I keep a streak going on Duolingo",
    "I've finished my dinner",
    "Give me a Python tip",
])
def test_goes_to_claude(said):
    assert router.route(said) is None


# ---------------------------------------------------------------------------
# Context handed to Claude
# ---------------------------------------------------------------------------
def test_context_mentions_shift_and_topic():
    router.route("I'm on backshift this week")
    ctx = memory.context()
    assert "Shift this week: backshift" in ctx
    assert "Current Python topic: Variables" in ctx
