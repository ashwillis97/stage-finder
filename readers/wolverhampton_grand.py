"""Reader for Wolverhampton Grand Theatre (https://www.grandtheatre.co.uk/whats-on/, /page/2/ ...)."""
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

THEATRE = "Wolverhampton Grand Theatre"
BASE = "https://www.grandtheatre.co.uk/"
_SKIP = re.compile(r"\bworkshops?\b|memory caf|members'? (event|evening)|members event|\bmasterclass(es)?\b|\bclasses\b|friends of the grand", re.I)
_P = re.compile(r"(\d{1,2})\s+([A-Za-z]{3,9})\.?(?:\s+(\d{4}))?")


def _range(text):
    """'24 Oct 2026' | '21 Oct–24 Oct 2026' | '28 Nov–03 Jan 2027' (year on the end date)."""
    found = [(int(d), _month(m), int(y) if y else None) for d, m, y in _P.findall(text or "")]
    found = [f for f in found if f[1]]
    if not found:
        return None
    a, b = found[0], found[-1]
    by = b[2] or _infer_year(b[1])
    ay = a[2] or (by - 1 if a[1] > b[1] else by)
    s, e = _mk(ay, a[1], a[0]), _mk(by, b[1], b[0])
    if not s or not e:
        return None
    return s, max(s, e)


def parse(html, url=BASE + "whats-on/"):
    results, seen = [], set()
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        return results
    for card in soup.select(".c-event-card"):
        try:
            h = card.select_one(".c-event-card__heading")
            a = (h.find_parent("a") if h else None) or card.find("a", href=True)
            if not h or not a or not a.get("href"):
                continue
            title = _tidy(h.get_text(" ", strip=True))
            if not title or _SKIP.search(title) or re.search(r"\bcancel+ed\b", card.get_text(" ", strip=True), re.I):
                continue
            d = card.select_one(".c-event-card__date")
            rng = _range(d.get_text(" ", strip=True)) if d else None
            if not rng:
                continue
            link = urljoin(BASE, a["href"].strip())
            if (link, rng[0]) in seen:
                continue
            seen.add((link, rng[0]))
            results.append({"title": title, "theatre": THEATRE, "genre": "",
                            "start": _iso(rng[0]), "end": _iso(rng[1]), "url": link})
        except Exception:
            continue
    return results
