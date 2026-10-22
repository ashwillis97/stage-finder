"""Reader for The Old Rep Theatre (https://www.oldrep.co.uk/whats-on/)."""
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

THEATRE = "The Old Rep Theatre"
BASE = "https://www.oldrep.co.uk/"
_SKIP = re.compile(r"\b(workshops?|masterclass(es)?|classes|guided tour|heritage tour|backstage tour|members'? (event|evening))\b|open mic", re.I)
_P = re.compile(r"(\d{1,2})(?:\s+([A-Za-z]{3,9}))?(?:\s+(\d{4}))?")


def _range(text):
    """'22 Oct 2026' | '7 - 8 Dec 2026' | '21 Nov - 31 Dec 2026' | '27 Feb - 6 Mar 2027'."""
    text = (text or "").strip()
    parts = re.split(r"\s*[-–—]\s*", text)
    parsed = []
    for p in parts[:2]:
        mo = _P.fullmatch(p.strip())
        if not mo:
            return None
        parsed.append([int(mo.group(1)), _month(mo.group(2)) if mo.group(2) else None,
                       int(mo.group(3)) if mo.group(3) else None])
    last = parsed[-1]
    if last[1] is None:
        return None
    for p in parsed:
        if p[1] is None:
            p[1] = last[1]
    if last[2] is None:
        last[2] = _infer_year(last[1])
    first = parsed[0]
    if first[2] is None:
        first[2] = last[2] - 1 if first[1] > last[1] else last[2]
    s, e = _mk(first[2], first[1], first[0]), _mk(last[2], last[1], last[0])
    if not s or not e:
        return None
    return s, max(s, e)


def parse(html, url=BASE + "whats-on/"):
    results, seen = [], set()
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        return results
    for card in soup.select(".eventwrapper"):
        try:
            a = card.find("a", href=True)
            h = card.find(["h4", "h3", "h2"])
            if not a or not h:
                continue
            title = _tidy(h.get_text(" ", strip=True))
            if not title or _SKIP.search(title) or re.search(r"\bcancel+ed\b", card.get_text(" ", strip=True), re.I):
                continue
            d = card.select_one(".date")
            rng = _range(d.get_text(" ", strip=True)) if d else None
            if not rng:
                continue
            genre = ""
            for c in card.get("class", []):
                if c.startswith("genre_") and len(c) > 6:
                    genre = " ".join(w.capitalize() for w in re.split(r"[-_]+", c[6:]) if w)
            link = urljoin(BASE, a["href"].strip())
            if (link, rng[0]) in seen:
                continue
            seen.add((link, rng[0]))
            results.append({"title": title, "theatre": THEATRE, "genre": genre,
                            "start": _iso(rng[0]), "end": _iso(rng[1]), "url": link})
        except Exception:
            continue
    return results
