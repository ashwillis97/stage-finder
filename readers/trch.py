"""Reader for Theatre Royal & Royal Concert Hall, Nottingham (trch.co.uk/whats-on).

Note: the listing is paginated (?p54_page=N); a single snapshot holds one page only.
"""
import re
from datetime import date
from urllib.parse import urljoin

from bs4 import BeautifulSoup

TODAY = date(2026, 10, 21)
_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
_DATE_RE = re.compile(
    r"(\d{1,2})(?:st|nd|rd|th)?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?(?:,?\s+(\d{4}))?",
    re.I)
_SMALL = {"a", "an", "and", "at", "but", "by", "for", "in", "of", "on", "or", "the", "to", "with", "vs"}
_NON_SHOW = re.compile(
    r"\b(tours?|workshops?|classes|class|masterclass(?:es)?|screenings?|film|cinema|courses?|"
    r"drop-?in|pre[- ]performance|forum|talk-?back)\b", re.I)


def _mk(y, m, d):
    try:
        return date(y, m, d)
    except ValueError:
        return None


def parse_range(text, today=TODAY):
    """Return (start, end) dates from text such as 'Wed 21 Oct - Sat 24 Oct 2026'."""
    toks = _DATE_RE.findall(text or "")
    if not toks:
        return None
    if len(toks) > 2:
        toks = [toks[0], toks[-1]]

    def one(tok, year):
        d, mon, _ = tok
        return int(d), _MONTHS[mon.lower()[:3]], year

    last = toks[-1]
    d2, m2, _ = one(last, None)
    if last[2]:
        y2 = int(last[2])
    else:
        y2 = today.year + (1 if m2 < today.month else 0)
    end = _mk(y2, m2, d2)
    if end is None:
        return None
    if len(toks) == 1:
        return end, end
    first = toks[0]
    d1, m1, _ = one(first, None)
    y1 = int(first[2]) if first[2] else y2
    start = _mk(y1, m1, d1)
    if start is None:
        return None
    if start > end and not first[2]:
        start = _mk(y1 - 1, m1, d1) or start
    if start > end:
        return None
    return start, end


def tidy_title(t):
    t = re.sub(r"[™®]", "", t or "")
    t = re.sub(r"\s+", " ", t).strip()
    letters = [c for c in t if c.isalpha()]
    if len(letters) > 3 and sum(c.isupper() for c in letters) / len(letters) > 0.8:
        words = t.lower().split(" ")
        out = []
        for i, w in enumerate(words):
            if i and w in _SMALL:
                out.append(w)
            else:
                out.append(re.sub(r"(^|[-'(\"/])([a-z])", lambda m: m.group(1) + m.group(2).upper(), w))
        t = " ".join(out)
    return t


def is_cancelled(text):
    return bool(re.search(r"\bcancel+ed\b|\bcancelled\b", text or "", re.I))


def _text(el):
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)) if el is not None else ""


_DEFAULT_THEATRE = "Theatre Royal Nottingham"
_IGNORE_GENRE = re.compile(r"discount|recently announced|west end shows", re.I)


def _venue(loc, href):
    s = (loc or "").lower()
    if "concert hall" in s:
        return "Royal Concert Hall"
    if "theatre royal" in s:
        return "Theatre Royal Nottingham"
    h = (href or "").lower()
    if "concert-hall" in h or "rch" in h.split("/")[-1].split("-"):
        return "Royal Concert Hall"
    return _DEFAULT_THEATRE


def parse(html, url):
    soup = BeautifulSoup(html, "lxml")
    out, seen = [], set()
    for card in soup.select("li.eventCard"):
        try:
            title_el = card.select_one(".title")
            link = card.select_one("a.desc[href]") or card.select_one("a[href]")
            if title_el is None or link is None:
                continue
            title = tidy_title(_text(title_el))
            href = urljoin(url or "https://www.trch.co.uk/whats-on", link["href"])
            full = _text(card)
            if not title or is_cancelled(full) or _NON_SHOW.search(title):
                continue
            d = card.select_one(".top-date") or card.select_one(".datetime .date")
            rng = parse_range(_text(d))
            if not rng:
                continue
            genre = ""
            for g in card.select(".genres__link"):
                gt = _text(g)
                if gt and not _IGNORE_GENRE.search(gt):
                    genre = gt
                    break
            loc = _text(card.select_one(".location"))
            key = (title, href, rng)
            if key in seen:
                continue
            seen.add(key)
            out.append({"title": title, "theatre": _venue(loc, href), "genre": genre,
                        "start": rng[0].isoformat(), "end": rng[1].isoformat(), "url": href})
        except Exception:
            continue
    return out
