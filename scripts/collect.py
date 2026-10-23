"""Read the saved venue pages in snapshots/ and update shows.json.

Each venue has a reader below. A venue's old rows are replaced only when its
reader finds at least one show, so a broken page never wipes the listings.
"""
import datetime as dt, json, pathlib, re, sys
from zoneinfo import ZoneInfo
from bs4 import BeautifulSoup

ROOT = pathlib.Path(__file__).resolve().parent.parent
SNAP = ROOT / "snapshots"
TODAY = dt.datetime.now(ZoneInfo("Europe/London")).date()
if len(sys.argv) > 1:
    TODAY = dt.date.fromisoformat(sys.argv[1])

MONTHS = {m: i for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split(), 1)}
MONTH_RE = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*"


def text(el):
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)) if el else ""


def parse_dates(raw):
    """'Tue 20 - Sat 24 Oct, 2026' -> (start, end) as date objects, or None."""
    t = re.sub(r"\d{1,2}[:.]\d{2}\s*(am|pm)?|\b\d{1,2}\s*(am|pm)\b", " ", raw, flags=re.I)
    t = re.sub(r",\s*(20\d\d)", r" \1", t)
    parts = re.split(r"\s*[–—-]\s*|\s*&\s*|\s*,\s*|\s+to\s+|\s+and\s+", t.strip())
    items = []
    for p in parts:
        d = re.search(r"(?<![\d:])(\d{1,2})(?:st|nd|rd|th)?(?!\d)", re.sub(r"20\d\d", " ", p))
        if not d:
            continue
        m = re.search(r"\b" + MONTH_RE + r"\b", p, flags=re.I)
        y = re.search(r"\b(20\d\d)\b", p)
        items.append([int(d.group(1)), MONTHS[m.group(1).lower()] if m else None, int(y.group(1)) if y else None])
    if not items:
        return None
    for i in range(len(items) - 2, -1, -1):  # back-fill month and year from the right
        if items[i][1] is None:
            items[i][1] = items[i + 1][1]
        if items[i][2] is None and items[i + 1][2] is not None and items[i][1] == items[i + 1][1]:
            items[i][2] = items[i + 1][2]
    if items[-1][1] is None:
        return None
    dates = [None] * len(items)
    for i in range(len(items) - 1, -1, -1):
        d, m, y = items[i]
        try:
            if y is None:
                y = items[i + 1][2] if i + 1 < len(items) and dates[i + 1] else None
            if y is None:
                y = TODAY.year
                cand = dt.date(y, m, d)
                if cand < TODAY - dt.timedelta(days=45):
                    y += 1
            cur = dt.date(y, m, d)
            if i + 1 < len(items) and dates[i + 1] and cur > dates[i + 1]:
                cur = dt.date(y - 1, m, d)
            dates[i] = cur
        except ValueError:
            return None
    return min(dates), max(dates)


def row(title, theatre, rng, url, genre=""):
    title = re.sub(r"\s+", " ", title).strip()
    if not title or not rng or not url:
        return None
    return {"title": title, "theatre": theatre, "genre": genre.strip(), "start": rng[0].isoformat(),
            "end": rng[1].isoformat(), "url": url}


def soup(name):
    p = SNAP / name
    if not p.exists():
        return None
    return BeautifulSoup(p.read_text(encoding="utf-8"), "lxml")


def files(prefix):
    return sorted(p.name for p in SNAP.glob(prefix + "-*.html"))


def select_all(prefix, css):
    return [x for f in files(prefix) for x in soup(f).select(css)]


def absu(base, href):
    from urllib.parse import urljoin
    return urljoin(base, href) if href else ""


SKIP = re.compile(r"workshop|open mic|heritage tour|members|memory caf|touch tour|backstage tour|exhibition on screen|"
                  r"^spotlight|young performers|theatre tour|co-working|^amplify|writing compelling|class\b|masterclass|talk and tour", re.I)


def read_dmh():
    out = []
    for f in files("de-montfort-hall"):
        for c in soup(f).select(".card-event, .feature-event"):
            a = c.select_one(".title a, h2 a, h3 a")
            d = c.select_one(".date, .dates")
            if not (a and d):
                continue
            title = text(a).title() if text(a).isupper() else text(a)
            if re.search(r"cancel", text(c), re.I):
                continue
            out.append(row(title, "De Montfort Hall", parse_dates(text(d)), absu("https://www.demontforthall.co.uk", a.get("href")), text(c.select_one(".category"))))
    return out


def read_grand():
    out = []
    for f in files("wolverhampton-grand"):
        for c in soup(f).select(".c-event-card"):
            a = c.select_one("a[href]")
            h = c.select_one(".c-event-card__heading")
            d = c.select_one(".c-event-card__date")
            if h and d and a:
                out.append(row(text(h), "Wolverhampton Grand Theatre", parse_dates(text(d)), a["href"]))
    return out


def read_century():
    out = []
    for c in select_all("century-theatre", "div[data-start-date]"):
        a = c.select_one("a.event_box")
        t = c.select_one(".title")
        if not (a and t):
            continue
        s, e = c.get("data-start-date"), c.get("data-end-date") or c.get("data-start-date")
        rng = (dt.datetime.strptime(s, "%Y%m%d").date(), dt.datetime.strptime(e, "%Y%m%d").date())
        out.append(row(text(t), "Century Theatre", rng, a["href"]))
    return out


def read_oldrep():
    out = []
    for c in select_all("old-rep", ".eventwrapper"):
        a = c.select_one("a[href]")
        t = c.select_one("h4")
        d = c.select_one(".date")
        if not (a and t and d):
            continue
        g = next((k[6:] for k in c.get("class", []) if k.startswith("genre_")), "")
        out.append(row(text(t), "The Old Rep Theatre", parse_dates(text(d)), absu("https://www.oldrep.co.uk", a["href"]), g.title()))
    return out


def read_curve():
    out = []
    for c in select_all("curve", "article.listing__item"):
        a = c.select_one("a[href]")
        t = c.select_one(".media__title")
        d = c.select_one(".show__date")
        if a and t and d:
            out.append(row(text(t), "Curve Theatre", parse_dates(text(d)), a["href"]))
    return out


def read_derby():
    out = []
    for c in select_all("derby-theatre", "div.card--event"):
        a = c.select_one("a.card-link")
        t = c.select_one("h3")
        d = c.select_one(".date")
        if a and t and d:
            out.append(row(text(t), "Derby Theatre", parse_dates(text(d)), a["href"], text(c.select_one(".category"))))
    return out


def read_playhouse():
    out = []
    for t in select_all("nottingham-playhouse", ".image-text-card-title"):
        box = t.parent
        a = t.select_one("a")
        d = box.select_one(".image-text-card-date")
        if a and d:
            out.append(row(text(a), "Nottingham Playhouse", parse_dates(text(d)), a["href"], text(box.select_one(".image-text-card-type"))))
    return out


def read_rep():
    out = []
    for c in select_all("the-rep", ".c-event-card"):
        a = c.select_one("a.c-event-card__link")
        t = c.select_one(".c-event-card__title")
        d = c.select_one(".c-event-card__daterange")
        if a and t and d:
            out.append(row(text(t), "The Rep", parse_dates(text(d)), a["href"]))
    return out


def read_hippodrome():
    out = []
    for c in select_all("hippodrome", ".performance-listing"):
        a = c.select_one("a.performance-listing-permalink")
        t = c.select_one(".performance-listing-title")
        d = c.select_one(".performance-listing-date")
        if a and t and d:
            out.append(row(text(t), "Birmingham Hippodrome", parse_dates(text(d)), a["href"], text(c.select_one(".performance-listing-genre"))))
    return out


def read_trch():
    out = []
    for c in select_all("trch", "li.eventCard"):
        a = c.select_one("a.desc")
        t = c.select_one(".title")
        d = c.select_one(".top-date .start")
        loc = text(c.select_one(".location"))
        if not (a and t and d):
            continue
        theatre = "Royal Concert Hall" if "Concert Hall" in loc else "Theatre Royal Nottingham"
        out.append(row(text(t), theatre, parse_dates(text(d)), absu("https://www.trch.co.uk", a["href"]), text(c.select_one(".genres__link"))))
    return out


FILM = re.compile(r"\((U|PG|12A?|15|18)\)\s*$")


def read_bonington():
    out = []
    for c in select_all("bonington", "li.WhatsonItem"):
        a = c.select_one("h3 a")
        d = c.select_one(".DateText")
        if not (a and d):
            continue
        if FILM.search(text(a)):
            continue
        out.append(row(text(a), "Bonington Theatre", parse_dates(text(d)), a["href"]))
    return out


def read_vaillant():
    out = []
    for c in select_all("vaillant-live", "div.item"):
        a = c.select_one("a.title")
        mo, dy = c.select_one(".mini-date-container .month"), c.select_one(".mini-date-container .day")
        if not (a and mo and dy):
            continue
        if re.search(r"darts|snooker|boxing|wrestling", text(a), re.I):
            continue
        out.append(row(text(a), "Vaillant Live", parse_dates(f"{text(dy)} {text(mo)}"), absu("https://vaillantlive.co.uk", a["href"])))
    return out


def each(prefix):
    for f in files(prefix):
        s = soup(f)
        if s is not None:
            yield s


DATE_IN_TEXT = re.compile(r"(Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*\.?,?\s+\d{1,2}\s+[A-Z][a-z]{2}")


BADGE = re.compile(r"^(sold out|low availability|selling fast|last tickets|few tickets left|new|on sale now|just announced)$", re.I)


def read_atg(prefix, theatre):
    out = []
    for s in each(prefix):
        for c in s.select("div.MuiPaper-root"):
            links = [a["href"] for a in c.find_all("a", href=True) if "/shows/" in a["href"] and not a["href"].rstrip("/").endswith("calendar")]
            if not links:
                continue
            parts = [p.strip() for p in c.get_text("|", strip=True).split("|") if p.strip() and not BADGE.match(p.strip())]
            date = next((p for p in parts if DATE_IN_TEXT.match(p)), None)
            if not date or not parts:
                continue
            title = parts[0]
            genre = parts[2] if len(parts) > 2 and not DATE_IN_TEXT.match(parts[2]) else ""
            if re.search(r"tour|gift|voucher|hospitality|experience package", title, re.I):
                continue
            out.append(row(title, theatre, parse_dates(date), absu("https://www.atgtickets.com", links[0]), genre))
    return out


def read_alexandra():
    return read_atg("alexandra", "The Alexandra Theatre")


def read_regent():
    return read_atg("regent-stoke", "Regent Theatre Stoke")


def read_newvic():
    out = []
    for s in each("new-vic"):
        for c in s.select("div.col-sm-6:has(.feature__content.event)"):
            body = c.select_one(".feature__content.event")
            a = body.select_one("a[href]")
            d = body.select_one("h2")
            parts = [p.strip() for p in c.get_text("|", strip=True).split("|") if p.strip()]
            if a and d and parts:
                out.append(row(parts[0], "New Vic Theatre", parse_dates(text(d)), a["href"]))
    return out


WW_CATS = {"Christmas & New Year", "Comedy", "Community & Amateur", "Dance", "Drama & Musical Theatre", "Family & Panto", "Music",
           "Opera, Orchestral, Choral", "Psychic & Magic", "Schools", "Talks", "Variety & Cabaret"}


def read_winding_wheel():
    out = []
    day = re.compile(r"^(Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*\.?,?\s+\d")
    for c in select_all("winding-wheel", "a.show-list-item"):
        t = c.select_one(".show-list-item__title")
        parts = [p.strip() for p in c.get_text("|", strip=True).split("|") if p.strip()]
        date = next((p for p in parts if day.match(p)), None)
        if not (t and date and c.get("href")):
            continue
        if not any("Winding Wheel" in p for p in parts):
            continue
        tags = [p for p in parts if p not in ("Info & Tickets", "Theatre Tokens", "Accessible", "Winding Wheel Theatre") and p != text(t) and p != date and not day.match(p)]
        cats = [g for g in tags if g in WW_CATS]
        genre = next((g for g in cats if g != "Community & Amateur"), cats[0] if cats else "")
        if "Cinema" in tags:
            continue
        out.append(row(text(t), "Winding Wheel Theatre", parse_dates(date), absu("https://chesterfieldtheatres.co.uk", c["href"]), genre))
    return out


def read_forest_live():
    out = []
    raw = (SNAP / "forest-live-cannock-1.html").read_text(encoding="utf-8")
    i = raw.find("contentListItemsV2")
    seg = raw[i:i + 20000].replace('\\"', '"').replace("\\u0026", "&") if i >= 0 else ""
    for title, sub, url, date in re.findall(
            r'"title":"([^"]*)","subtitle":"([^"]*)","caption":"[^"]*","ctaLabel":"[^"]*","ctaUrl":"([^"]*)"[^\]]*?"label":"(\d{1,2} [A-Za-z]+ \d{4})"', seg):
        out.append(row(f"{title} {sub}".strip(), "Forest Live Cannock Chase", parse_dates(date), absu("https://www.forestlive.com", url), "Concert"))
    return out


def read_big_top():
    s = soup("big-top-arena-1.html")
    if s is None:
        return []
    t = re.sub(r"\s+", " ", s.get_text(" | ", strip=True))
    m = re.search(r"what's on \| (.+?) \| ([A-Z]+ \d+(?:ST|ND|RD|TH)? ?- ?[A-Z]+ \d+(?:ST|ND|RD|TH)? 20\d\d)", t)
    link = next((a["href"] for a in s.find_all("a", href=True) if "tickets" in a["href"]), "")
    if not m or not link:
        return []
    return [row(m.group(1).title(), "Big Top Arena", parse_dates(m.group(2)), link, "Musical")]


SPORT = re.compile(r"\bvs?\b|panthers|netball|hockey|boxing|wrestling|darts|snooker|basketball|ice hockey|eihl|play-?offs?", re.I)


def read_motorpoint():
    out = []
    for c in select_all("motorpoint-arena", 'a[class*="EventCard"][class*="__item"]'):
        t = c.select_one('[class*="card__title"]')
        d = c.select_one('[class*="card__date"]')
        if not (t and d) or SPORT.search(text(t)):
            continue
        out.append(row(text(t).title() if text(t).isupper() else text(t), "Motorpoint Arena Nottingham", parse_dates(text(d)), c["href"]))
    return out


READERS = {
    "De Montfort Hall": read_dmh, "Wolverhampton Grand Theatre": read_grand, "Century Theatre": read_century,
    "The Old Rep Theatre": read_oldrep, "Curve Theatre": read_curve, "Derby Theatre": read_derby,
    "Nottingham Playhouse": read_playhouse, "The Rep": read_rep, "Birmingham Hippodrome": read_hippodrome,
    "TRCH": read_trch, "The Alexandra Theatre": read_alexandra, "Regent Theatre Stoke": read_regent, "New Vic Theatre": read_newvic, "Winding Wheel Theatre": read_winding_wheel, "Forest Live Cannock Chase": read_forest_live, "Big Top Arena": read_big_top, "Motorpoint Arena Nottingham": read_motorpoint, "Bonington Theatre": read_bonington, "Vaillant Live": read_vaillant,
}

REMOVED = {"Repton 400 Hall Theatre", "Elite Cinema and Theatre"}  # venues the owner dropped

GENRE_HINTS = [(r"tribute|story of|legends|experience", "Tribute"), (r"orchestra|philharmon|symphony|concert", "Classical"),
               (r"comedy|stand.?up|live at", "Comedy"), (r"musical", "Musical"), (r"panto|cinderella|beauty and the beast|puss in boots|goldilocks|treasure island|jack and the beanstalk", "Pantomime"),
               (r"christmas|carol", "Christmas")]


def main():
    path = ROOT / "shows.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    old = [r for r in data["shows"] if r["theatre"] not in REMOVED]
    old_genre = {(r["title"].lower(), r["theatre"]): r.get("genre", "") for r in old}
    fresh, stale = {}, []
    for name, fn in READERS.items():
        try:
            rows = [r for r in fn() if r]
        except Exception as e:  # keep going; a broken reader must not stop the others
            print(f"{name}: reader failed: {e!r}")
            rows = []
        rows = [r for r in rows if r["end"] >= TODAY.isoformat() and not SKIP.search(r["title"])]
        print(f"{name}: {len(rows)} shows")
        if not rows:
            stale.append(name)
            continue
        for r in rows:
            if not r["genre"]:
                r["genre"] = old_genre.get((r["title"].lower(), r["theatre"]), "")
            if not r["genre"]:
                r["genre"] = next((g for rx, g in GENRE_HINTS if re.search(rx, r["title"], re.I)), "")
            fresh.setdefault(r["theatre"], []).append(r)
    kept = [r for r in old if r["theatre"] not in fresh and r["end"] >= TODAY.isoformat()]
    merged, seen = [], set()
    for r in kept + [x for v in fresh.values() for x in v]:
        k = (r["title"].lower(), r["theatre"], r["start"])
        if k not in seen:
            seen.add(k)
            merged.append(r)
    merged.sort(key=lambda r: (r["start"], r["title"]))
    data["shows"] = merged
    cov = data.setdefault("coverage", {"none": [], "partial": {}})
    part = cov.setdefault("partial", {})
    auto_note = "Not updated automatically yet, so these listings may be out of date."
    scraped = set(fresh)
    keep_notes = {"Theatre Royal Nottingham", "Royal Concert Hall"}
    for t in list(part):
        if t in scraped and t not in keep_notes:
            del part[t]
    for t in {r["theatre"] for r in merged} - scraped:
        part[t] = auto_note
    for t in stale:
        pass
    cov["none"] = [n for n in cov.get("none", []) if n not in scraped and n not in REMOVED]
    for t in REMOVED:
        part.pop(t, None)
    data["sample"] = False
    data["updated"] = dt.datetime.now(ZoneInfo("Europe/London")).isoformat(timespec="minutes")
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(merged)} shows written; venues not refreshed: {stale}")


if __name__ == "__main__":
    main()
