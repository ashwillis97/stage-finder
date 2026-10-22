"""Reader for Birmingham Repertory Theatre (birmingham-rep.co.uk/whats-on/).

Note: paginated (/whats-on/page/N/); the page repeats some cards, so de-duplicated by URL.
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


_HUB = re.compile(r"^the hub$", re.I)


def parse(html, url):
    soup = BeautifulSoup(html, "lxml")
    out, seen = [], set()
    base = url or "https://www.birmingham-rep.co.uk/whats-on/"
    for card in soup.select(".c-event-card"):
        try:
            link = card.select_one("a.c-event-card__link[href]") or card.select_one("a[href]")
            t_el = card.select_one(".c-event-card__title")
            if link is None or t_el is None:
                continue
            title = tidy_title(_text(t_el))
            href = urljoin(base, link["href"])
            slug = href.rstrip("/").rsplit("/", 1)[-1].replace("-", " ")
            venue = _text(card.select_one(".c-event-card-venue__text"))
            if not title or is_cancelled(_text(card)):
                continue
            if _NON_SHOW.search(title) or _NON_SHOW.search(slug) or _HUB.match(venue) \
                    or re.search(r"play in a day", title, re.I):
                continue
            rng = parse_range(_text(card.select_one("time")))
            if not rng:
                continue
            if href in seen:
                continue
            seen.add(href)
            out.append({"title": title, "theatre": "The Rep", "genre": "",
                        "start": rng[0].isoformat(), "end": rng[1].isoformat(), "url": href})
        except Exception:
            continue
    return out
