"""
Jarvis router - Tier 1: instant answers with no AI.

route(text) checks what you said against a list of rules. If one matches, it reads or
updates your vault and returns a spoken reply straight away. If nothing matches it
returns None, and the request goes to Claude (Tier 2).

Every rule is a small function. To add your own: write a function that takes the
cleaned-up text and returns a reply string (or None), and add it to RULES at the bottom.
"""

import re
from datetime import datetime

import memory

# ---------------------------------------------------------------------------
# Understanding spoken numbers and durations
# ---------------------------------------------------------------------------
NUMBER_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20,
    "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}


def words_to_digits(text):
    """'forty five minutes' -> '45 minutes', 'an hour' -> '1 hour'."""
    text = re.sub(r"\b(an?) (hour|hr)\b", r"1 \2", text)
    out, total, in_number = [], 0, False
    for word in re.split(r"(\s+|-)", text):
        w = word.strip().lower()
        if w in NUMBER_WORDS:
            total += NUMBER_WORDS[w]
            in_number = True
        elif in_number and w in ("", "-"):
            continue
        else:
            if in_number:
                out.append(f"{total} ")
                total, in_number = 0, False
            out.append(word)
    if in_number:
        out.append(str(total))
    return "".join(out)


def parse_minutes(text):
    """Find a duration in text and return it in minutes, or None."""
    if re.search(r"\bhalf an? hour\b", text.lower()) and not re.search(r"\band a half\b", text.lower()):
        return 30
    t = words_to_digits(text.lower())
    m = re.search(r"\b(\d+(?:\.\d+)?)\s*(?:hours?|hrs?)\b(?:\s+and\s+(?:a\s+)?(half|(\d+)\s*(?:minutes?|mins?)))?", t)
    if m:
        minutes = float(m.group(1)) * 60
        if m.group(2) == "half":
            minutes += 30
        elif m.group(3):
            minutes += int(m.group(3))
        return round(minutes)
    m = re.search(r"\b(\d+)\s*(?:minutes?|mins?)\b", t)
    return int(m.group(1)) if m else None


def say_list(items):
    items = list(items)
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def plural(n, word):
    n = int(n) if float(n).is_integer() else n
    return f"{n} {word}" + ("" if n == 1 else "s")


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------
def log_study(t):
    if t.startswith(("how", "what", "why", "when", "can", "should")):
        return None
    explicit = re.search(r"\b(log|logged|record)\b", t)
    studyish = (re.search(r"\b(studied|did|done|put in|spent)\b", t)
                and re.search(r"\b(python|study|studying|coding|code|learning)\b", t))
    if not (explicit or studyish):
        return None
    minutes = parse_minutes(t)
    if not minutes:
        return None
    topic = re.search(r"(?:minutes?|mins?|hours?|hrs?|half)\s+(?:of|on)\s+(.+)$", words_to_digits(t))
    topic = topic.group(1).strip() if topic else ""
    if topic in ("python", "study", "studying", "coding"):
        topic = "Python" if topic == "python" else ""
    memory.log_study(minutes, topic)
    return (f"Logged {plural(minutes, 'minute')}. That's {plural(memory.week_hours(), 'hour')} this week "
            f"and a {memory.streak()}-day streak.")


def ask_streak(t):
    if not re.search(r"\bmy streak\b|^streak$|\bstreak (am i|is it)\b|\bhow long is my streak\b", t):
        return None
    n = memory.streak()
    if n == 0:
        return "No streak yet. Log a study session to start one."
    return f"You're on a {n}-day streak. Don't break it."


def ask_week(t):
    if not (re.search(r"how (many|much) (hours|time)|hours this week|studied this week|^my week$|how'?s my week", t)
            and re.search(r"stud|this week|my week|python", t)):
        return None
    hours, target = memory.week_hours(), memory.STUDY_TARGET_HOURS
    left = round(target - hours, 1)
    if left <= 0:
        return f"{plural(hours, 'hour')} this week. Target smashed."
    return f"{plural(hours, 'hour')} this week, out of {target}. {plural(left, 'hour')} to go."


SHIFTS = {
    "back": "backshift", "backs": "backshift", "nights": "nightshift", "night": "nightshift",
    "days": "dayshift", "day": "dayshift", "early": "earlies", "earlies": "earlies",
    "late": "lates", "lates": "lates", "off": "off",
}


def set_shift(t):
    m = re.search(r"\b(?:i'?m|i am|i'll be|im)\s+(?:on\s+)?(?:the\s+)?(back|backs|nights?|days?|early|earlies|lates?|off)"
                  r"\s*(?:shift)?\b.*\b(this|next) week\b", t.replace("backshift", "back shift")
                  .replace("nightshift", "night shift").replace("dayshift", "day shift"))
    if not m:
        return None
    name = SHIFTS[m.group(1)]
    memory.set_shift(name, next_week=m.group(2) == "next")
    if name == "off":
        return f"Got it, you're off {m.group(2)} week. Good time to get some study hours in."
    return f"Got it, {name} {m.group(2)} week. I'll plan around it."


def ask_shift(t):
    if not re.search(r"\b(what|which) shift\b|\bmy shift\b", t):
        return None
    shift = memory.get_shift()
    if not shift:
        return "You haven't told me this week's shift. Say something like, I'm on backshift this week."
    return "You're off this week." if shift == "off" else f"You're on {shift} this week."


def add_task(t):
    m = (re.match(r"^(?:add|new)\s+(?:a\s+)?(?:task|directive|to-?do)\s*(?:to my list)?[:,]?\s+(.+)$", said, re.I)
         or re.match(r"^(?:add|put)\s+(.+?)\s+(?:to|on)\s+my\s+(?:list|tasks|directives|to-?do list)$", said, re.I))
    if not m:
        return None
    text = memory.add_directive(re.sub(r"^to\s+", "", m.group(1), flags=re.I))
    return f"Added to your list: {text}."


def list_tasks(t):
    if not re.search(r"what'?s (?:next )?on my (list|plate)|\bmy (tasks|directives|to-?dos?|to-?do list)\b|what do i (need|have) to do", t):
        return None
    todo = [d["text"] for d in memory.directives() if not d["done"]]
    if not todo:
        return "Your list's clear."
    return f"{plural(len(todo), 'thing')} on your list: {say_list(todo)}."


def ask_roadmap(t):
    if not (re.search(r"^what'?s next$|what (am i|should i be|should i) (learning|studying|study)|\broadmap\b|current topic", t)
            or (re.search(r"what'?s next", t) and re.search(r"python|learn|study|topic", t))):
        return None
    road = memory.roadmap()
    if not road["next"] and road["current"] == "Roadmap complete":
        return "You've finished the whole roadmap. Time to add some harder topics."
    reply = f"You're on {road['current']}."
    if road["next"]:
        reply += f" After that, {road['next'][0]}."
    return reply


def mark_done(t):
    """'tick off github', 'I've finished lists' -> ticks a task, or failing that a roadmap topic."""
    if re.search(r"^(?:next topic|move on to the next topic|i'?ve finished (?:this|the current) topic)$", t):
        done = memory.complete_topic()
        return f"Nice one. {done} is done. Next up: {memory.roadmap()['current']}." if done else None
    m = (re.match(r"^(?:tick off|cross off|i'?ve done|i have done|done with|i'?ve finished|i have finished|finished)\s+(?:the\s+)?(.+)$", t)
         or re.match(r"^mark\s+(.+?)\s+(?:as\s+)?(?:done|complete)$", t))
    if not m:
        return None
    task = memory.complete_directive(m.group(1))
    if task:
        return f"Ticked off: {task}."
    topic = memory.complete_topic(m.group(1))
    if topic:
        return f"Nice one. {topic} is done. Next up: {memory.roadmap()['current']}."
    return None


def log_application(t):
    m = re.match(r"^i(?: have|'ve)? applied (?:for|to) (?:a |an |the )?(.+?)(?: (?:job|role|position))?(?: at (.+))?$", t)
    if not m:
        return None
    role, company = (m.group(1), m.group(2)) if m.group(2) else ("", m.group(1))
    memory.add_job(company.title(), role)
    n = memory.job_counts()["applied"]
    return f"Logged. That's {plural(n, 'application')} so far. Good luck with it."


def ask_applications(t):
    if not re.search(r"how many (applications|jobs)|job pipeline|my applications", t):
        return None
    c = memory.job_counts()
    return (f"{plural(c['applied'], 'application')} sent, {plural(c['interview'], 'interview')}"
            f" and {plural(c['offer'], 'offer')}.")


def ask_time(t):
    now = datetime.now()
    if re.search(r"^(?:what time is it|what'?s the time)(?: now)?$", t):
        return f"It's {now:%H:%M}."
    if re.search(r"^(?:what'?s the date|what day is it|what'?s today'?s date)(?: today)?$", t):
        return f"It's {now:%A} the {now.day} of {now:%B}."
    return None


# Order matters: the first rule that answers wins.
RULES = [
    log_study, ask_streak, ask_week, set_shift, ask_shift, add_task, mark_done, list_tasks,
    ask_roadmap, log_application, ask_applications, ask_time,
]


said = ""   # what was said, tidied but with its capital letters kept (for task text)


def clean(text):
    t = text.strip()
    t = t.replace("’", "'")
    t = re.sub(r"[.!?,]+$", "", t)
    t = re.sub(r"^(hey |ok |okay )?jarvis[,.!]?\s*", "", t, flags=re.I)
    return re.sub(r"\s+", " ", t)


def route(text):
    """Return an instant reply if a rule matches, otherwise None (Claude takes it)."""
    global said
    said = clean(text)
    t = said.lower()
    for rule in RULES:
        reply = rule(t)
        if reply:
            return reply
    return None
