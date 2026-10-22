"""Reader for Century Theatre, Coalville (https://centurytheatre.co.uk/whats-on/)."""
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

THEATRE = "Century Theatre"
BASE = "https://centurytheatre.co.uk/"
_SKIP = re.compile(r"open mic|heritage tour|\bguided tour\b|community chat|signers club|\bworkshops?\b", re.I)


def _d8(s):
    s = (s or "").strip()
    if re.fullmatch(r"\d{8}", s):
        return _mk(int(s[:4]), int(s[4:6]), int(s[6:]))
    return None


def parse(html, url=BASE + "whats-on/"):
    results, seen = [], set()
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        return results
    for card in soup.select("[data-start-date]"):
        try:
            a = card.find("a", href=True)
            t = card.select_one(".title")
            if not a or not t:
                continue
            title = _tidy(t.get_text(" ", strip=True))
            if not title or _SKIP.search(title) or re.search(r"\bcancel+ed\b", card.get_text(" ", strip=True), re.I):
                continue
            start = _d8(card.get("data-start-date"))
            if not start:
                continue
            end = _d8(card.get("data-end-date")) or start
            if end < start:
                end = start
            link = urljoin(BASE, a["href"].strip())
            if (link, start) in seen:
                continue
            seen.add((link, start))
            results.append({"title": title, "theatre": THEATRE, "genre": "",
                            "start": _iso(start), "end": _iso(end), "url": link})
        except Exception:
            continue
    return results
