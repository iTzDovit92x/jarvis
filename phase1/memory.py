"""
Jarvis memory: plain markdown files in data/vault.

You can open the vault in Obsidian ("Open folder as vault") or just edit the files in Notepad.
Jarvis reads them fresh every time, so your edits show up straight away.

    vault/
      directives.md           - your to-do list (- [ ] / - [x])
      shift.md                - this week's shift
      wire.md                 - AI wire items for the HUD
      learning/study-log.md   - one line per study session
      learning/roadmap.md     - Python topics in order (- [ ] / - [x])
      jobs/pipeline.md        - one line per job: status | company | role | date
      daily/2026-10-31.md     - every request Jarvis handled that day
"""

import re
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path

STUDY_TARGET_HOURS = 14
VAULT = None   # set by use_vault() below


def use_vault(path):
    """Point Jarvis at a vault folder (tests use a temporary one)."""
    global VAULT, STUDY_LOG, ROADMAP, DIRECTIVES, SHIFT, JOBS, WIRE, DAILY
    VAULT = Path(path)
    STUDY_LOG = VAULT / "learning" / "study-log.md"
    ROADMAP = VAULT / "learning" / "roadmap.md"
    DIRECTIVES = VAULT / "directives.md"
    SHIFT = VAULT / "shift.md"
    JOBS = VAULT / "jobs" / "pipeline.md"
    WIRE = VAULT / "wire.md"
    DAILY = VAULT / "daily"


use_vault(Path(__file__).parent / "data" / "vault")


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
def starter_files():
    return {
        DIRECTIVES: "# Directives\n\n- [ ] Push Jarvis to GitHub\n- [ ] 45 min Python: lists and dictionaries\n",
        SHIFT: "# Shift\n\nshift: not set\nweek_of: \n",
        WIRE: "# AI wire\n\n- [Phase 4] /ai-intel will fill this with GitHub trending and AI news.\n",
        STUDY_LOG: "# Study log\n\nOne line per session: date time | minutes | topic\n\n",
        ROADMAP: "# Python roadmap\n\nTick topics off as you finish them. The first unticked one is your current topic.\n\n"
                 + "".join(f"- [ ] {t}\n" for t in [
                     "Variables, types and f-strings", "Lists, dictionaries and loops", "Functions and scope",
                     "Files with pathlib", "Errors and try/except", "Modules and virtual environments",
                     "Classes and objects", "APIs and JSON with requests", "Testing with pytest",
                     "Async basics with asyncio", "Git and GitHub workflow", "Build an API with FastAPI"]),
        JOBS: "# Job pipeline\n\nOne line per job: status | company | role | date\nStatuses: found, applied, interview, offer, rejected\n\n",
    }


def setup(old_directives=None):
    """Create any missing vault files. old_directives carries over the to-do list from Phase 1's hud.json."""
    for path, text in starter_files().items():
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            if path == DIRECTIVES and old_directives:
                text = "# Directives\n\n" + "".join(
                    f"- [{'x' if d.get('done') else ' '}] {d['text']}\n" for d in old_directives)
            path.write_text(text, encoding="utf-8")
    DAILY.mkdir(parents=True, exist_ok=True)


def _read(path):
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _append(path, line):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def similar(a, b):
    """How alike two bits of text are, 0 to 1. Used to match 'tick off github' to 'Push Jarvis to GitHub'."""
    a, b = a.lower().strip(), b.lower().strip()
    if a and a in b:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


# ---------------------------------------------------------------------------
# Study
# ---------------------------------------------------------------------------
STUDY_LINE = re.compile(r"^- (\d{4}-\d{2}-\d{2})(?: \d{2}:\d{2})? \| (\d+) min(?: \| (.*))?$")


def log_study(minutes, topic="", when=None):
    when = when or datetime.now()
    line = f"- {when:%Y-%m-%d %H:%M} | {int(minutes)} min"
    if topic:
        line += f" | {topic}"
    _append(STUDY_LOG, line)


def minutes_by_day():
    totals = {}
    for line in _read(STUDY_LOG).splitlines():
        m = STUDY_LINE.match(line.strip())
        if m:
            day = date.fromisoformat(m.group(1))
            totals[day] = totals.get(day, 0) + int(m.group(2))
    return totals


def streak(today=None):
    """Days in a row with study logged. Today doesn't break it until it's over."""
    today = today or date.today()
    days = minutes_by_day()
    day = today if days.get(today) else today - timedelta(days=1)
    count = 0
    while days.get(day):
        count += 1
        day -= timedelta(days=1)
    return count


def week_hours(today=None):
    """Hours studied since Monday."""
    today = today or date.today()
    monday = today - timedelta(days=today.weekday())
    mins = sum(m for d, m in minutes_by_day().items() if monday <= d <= today)
    return round(mins / 60, 1)


def last_7_days(today=None):
    today = today or date.today()
    days = minutes_by_day()
    return [round(days.get(today - timedelta(days=i), 0) / 60, 2) for i in range(6, -1, -1)]


# ---------------------------------------------------------------------------
# Checklists (directives and roadmap use the same "- [ ] text" format)
# ---------------------------------------------------------------------------
CHECK_LINE = re.compile(r"^(\s*)- \[( |x|X)\] (.*)$")


def read_checklist(path):
    items = []
    for line in _read(path).splitlines():
        m = CHECK_LINE.match(line)
        if m:
            items.append({"text": m.group(3).strip(), "done": m.group(2).lower() == "x"})
    return items


def _set_done(path, index, done):
    """Tick or untick the index-th checklist line, leaving every other line as it was."""
    lines, seen = _read(path).splitlines(), -1
    for i, line in enumerate(lines):
        m = CHECK_LINE.match(line)
        if m:
            seen += 1
            if seen == index:
                lines[i] = f"{m.group(1)}- [{'x' if done else ' '}] {m.group(3)}"
                break
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _best_match(items, query, threshold=0.6):
    scored = [(similar(query, it["text"]), i) for i, it in enumerate(items)]
    if not scored:
        return None
    score, i = max(scored)
    return i if score >= threshold else None


# directives
def directives():
    return read_checklist(DIRECTIVES)


def add_directive(text):
    text = text.strip().rstrip(".")
    text = text[0].upper() + text[1:] if text else text
    _append(DIRECTIVES, f"- [ ] {text}")
    return text


def toggle_directive(index):
    items = directives()
    if 0 <= index < len(items):
        _set_done(DIRECTIVES, index, not items[index]["done"])


def complete_directive(query):
    """Tick off the open directive that best matches what was said. Returns its text, or None."""
    items = directives()
    open_items = [dict(it, i=i) for i, it in enumerate(items) if not it["done"]]
    pick = _best_match(open_items, query)
    if pick is None:
        return None
    _set_done(DIRECTIVES, open_items[pick]["i"], True)
    return open_items[pick]["text"]


# roadmap
def roadmap():
    items = read_checklist(ROADMAP)
    done = sum(it["done"] for it in items)
    upcoming = [it["text"] for it in items if not it["done"]]
    return {
        "current": upcoming[0] if upcoming else "Roadmap complete",
        "progress": round(done / len(items) * 100) if items else 0,
        "next": upcoming[1:4],
        "done": done,
        "total": len(items),
    }


def complete_topic(query=None):
    """Tick off a roadmap topic: the current one, or the one that best matches query."""
    items = read_checklist(ROADMAP)
    open_items = [dict(it, i=i) for i, it in enumerate(items) if not it["done"]]
    if not open_items:
        return None
    pick = 0 if query is None else _best_match(open_items, query)
    if pick is None:
        return None
    _set_done(ROADMAP, open_items[pick]["i"], True)
    return open_items[pick]["text"]


# ---------------------------------------------------------------------------
# Shift
# ---------------------------------------------------------------------------
def monday_of(day):
    return day - timedelta(days=day.weekday())


def set_shift(name, next_week=False, today=None):
    today = today or date.today()
    week = monday_of(today) + timedelta(days=7 if next_week else 0)
    SHIFT.write_text(f"# Shift\n\nshift: {name}\nweek_of: {week.isoformat()}\n", encoding="utf-8")


def get_shift(today=None):
    """This week's shift, or None if it hasn't been set for this week."""
    today = today or date.today()
    text = _read(SHIFT)
    name = re.search(r"^shift:\s*(.+)$", text, re.M)
    week = re.search(r"^week_of:\s*(\d{4}-\d{2}-\d{2})", text, re.M)
    if not name or not week or name.group(1).strip() == "not set":
        return None
    return name.group(1).strip() if date.fromisoformat(week.group(1)) == monday_of(today) else None


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------
JOB_LINE = re.compile(r"^- (found|applied|interview|offer|rejected) \| (.*?) \| (.*?) \| (\d{4}-\d{2}-\d{2})$")


def add_job(company, role="", status="applied", today=None):
    today = today or date.today()
    _append(JOBS, f"- {status} | {company.strip()} | {role.strip()} | {today.isoformat()}")


def job_counts():
    counts = {"found": 0, "applied": 0, "interview": 0, "offer": 0, "rejected": 0}
    for line in _read(JOBS).splitlines():
        m = JOB_LINE.match(line.strip())
        if m:
            counts[m.group(1)] += 1
    # everyone you've applied to counts as applied, even if they've since moved on
    counts["applied"] += counts["interview"] + counts["offer"] + counts["rejected"]
    return counts


# ---------------------------------------------------------------------------
# Wire + daily notes
# ---------------------------------------------------------------------------
def wire():
    items = []
    for line in _read(WIRE).splitlines():
        m = re.match(r"^- (?:\[(.+?)\] )?(.+)$", line.strip())
        if m:
            items.append({"tag": m.group(1) or "", "text": m.group(2)})
    return items


def log_request(you, jarvis, tier, secs, when=None):
    when = when or datetime.now()
    note = DAILY / f"{when:%Y-%m-%d}.md"
    if not note.exists():
        note.parent.mkdir(parents=True, exist_ok=True)
        note.write_text(f"# {when:%A %d %B %Y}\n\n## Log\n\n", encoding="utf-8")
    _append(note, f"- {when:%H:%M} · tier {tier} · {secs}s\n  - **You:** {you}\n  - **Jarvis:** {jarvis}")


# ---------------------------------------------------------------------------
# Everything the HUD shows, and a summary for Claude
# ---------------------------------------------------------------------------
def panels(today=None):
    today = today or date.today()
    return {
        "streak_days": streak(today),
        "study_last_7": last_7_days(today),
        "study_hours_week": week_hours(today),
        "study_target_hours": STUDY_TARGET_HOURS,
        "pipeline": job_counts(),
        "directives": directives(),
        "roadmap": roadmap(),
        "shift": get_shift(today),
        "wire": wire(),
    }


def context(today=None):
    """A few lines about where things stand, handed to Claude so its answers fit your week."""
    today = today or date.today()
    road, shift = roadmap(), get_shift(today)
    todo = [d["text"] for d in directives() if not d["done"]][:5]
    parts = [
        f"Today is {today:%A %d %B}.",
        f"Shift this week: {shift}." if shift else "Shift this week: not set.",
        f"Current Python topic: {road['current']} ({road['done']} of {road['total']} topics done).",
        f"Study streak: {streak(today)} days; {week_hours(today)} of {STUDY_TARGET_HOURS} hours this week.",
    ]
    if todo:
        parts.append("Open tasks: " + "; ".join(todo) + ".")
    return " ".join(parts)
