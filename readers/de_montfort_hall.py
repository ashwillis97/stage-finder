"""Reader for De Montfort Hall (https://www.demontforthall.co.uk/whats-on/), one page per call."""
import os
import re
from datetime import date
from urllib.parse import urljoin

from bs4 import BeautifulSoup

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
_ACRONYMS = {"uk", "usa", "bbc", "dj", "tv", "mc", "ii", "iii", "iv", "vip", "nhs"}
_SMALL = {"a", "an", "and", "as", "at", "but", "by", "for", "in", "of", "on", "or", "the", "to", "vs", "with"}


def _today():
    env = os.environ.get("STAGE_FINDER_TODAY")
    if env:
        try:
            return date.fromisoformat(env)
        except ValueError:
            pass
    return date.today()


def _month(s):
    return MONTHS.get(s[:3].lower())


def _mk(y, m, d):
    try:
        return date(y, m, d)
    except (TypeError, ValueError):
        return None


def _infer_year(m, today=None):
    """Year for a day/month with no year: month earlier than today's month -> next year."""
    today = today or _today()
    return today.year + 1 if m < today.month else today.year


def _tidy(title):
    """Collapse whitespace; title-case only if the site shouts in UPPERCASE."""
    t = re.sub(r"\s+", " ", (title or "")).strip()
    letters = [c for c in t if c.isalpha()]
    if len(letters) < 3 or any(c.islower() for c in letters):
        return t
    state = {"first": True}

    def fix(mo):
        w = mo.group(0)
        lw = w.lower()
        first = state["first"]
        state["first"] = False
        if lw in _ACRONYMS:
            return w
        if not first and lw in _SMALL:
            return lw
        return lw[:1].upper() + lw[1:]

    out = re.sub(r"[A-Za-zÀ-ſ]+(?:['’][A-Za-z]+)*", fix, t)
    # a word after a colon / dash starts a new clause: capitalise it
    out = re.sub(r"([:–—!?]\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), out)
    return out


def _iso(d):
    return d.isoformat()

THEATRE = "De Montfort Hall"
BASE = "https://www.demontforthall.co.uk/"
_SKIP = re.compile(r"\b(workshops?|masterclass(es)?|classes|class|guided tour|heritage tour|backstage tour|members'? (event|evening))\b", re.I)
_DATE = re.compile(r"(\d{1,2})\s+([A-Za-z]{3,9})\.?(?:\s+(\d{4}))?")


def _dates(text):
    found = []
    for d, mon, y in _DATE.findall(text or ""):
        m = _month(mon)
        if not m:
            continue
        found.append((int(d), m, int(y) if y else None))
    if not found:
        return None
    out = []
    for d, m, y in found[:2]:
        out.append(_mk(y or _infer_year(m), m, d))
    if None in out:
        return None
    start, end = out[0], out[-1]
    if end < start:
        end = start
    return start, end


def parse(html, url=BASE + "whats-on/"):
    results, seen = [], set()
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        return results
    for card in soup.select(".card-event"):
        try:
            a = card.select_one("h3.title a, .title a") or card.select_one("a.cta--secondary")
            if not a or not a.get("href"):
                continue
            title = _tidy(a.get_text(" ", strip=True))
            if not title or _SKIP.search(title):
                continue
            if re.search(r"\bcancel+ed\b", card.get_text(" ", strip=True), re.I):
                continue
            dt = _dates(card.select_one(".date").get_text(" ", strip=True) if card.select_one(".date") else "")
            if not dt:
                continue
            link = urljoin(BASE, a["href"].strip())
            cat = card.select_one(".category")
            genre = cat.get_text(" ", strip=True) if cat else ""
            key = (link, dt[0])
            if key in seen:
                continue
            seen.add(key)
            results.append({"title": title, "theatre": THEATRE, "genre": genre,
                            "start": _iso(dt[0]), "end": _iso(dt[1]), "url": link})
        except Exception:
            continue
    return results
