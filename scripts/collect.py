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

def _venue_files():
    for f in ("venues.json", "venues_new.json"):
        fp = ROOT / f
        if fp.exists():
            yield from json.loads(fp.read_text(encoding="utf-8"))["venues"]


for _v in _venue_files():  # venues flagged reader=atg need no custom code
    if _v.get("reader") == "atg" and _v["name"] not in READERS:
        READERS[_v["name"]] = (lambda s=_v["slug"], n=_v["name"]: read_atg(s, n))


def read_lw(prefix, theatre, match=None):
    """lwtheatres.co.uk cards: title | date range | venue."""
    out, seen = [], set()
    for s in each(prefix):
        for a in s.find_all("a", href=True):
            if "/whats-on/" not in a["href"] or a["href"].rstrip("/").endswith(("whats-on", "?all")):
                continue
            parts = [x.strip() for x in a.get_text("|", strip=True).split("|") if x.strip()]
            if len(parts) < 3 or (match or theatre).lower() not in parts[-1].lower():
                continue
            rng = parse_dates(parts[1])
            key = (parts[0], parts[1])
            if rng and key not in seen:
                seen.add(key)
                out.append(row(parts[0], theatre, rng, absu("https://lwtheatres.co.uk", a["href"])))
    return out


def read_trafalgar(prefix, theatre):
    """trafalgartickets.com venue pages: [badge] | category | title | date parts | from | price."""
    out = []
    for s in each(prefix):
        for a in s.find_all("a", href=True):
            if "/event/" not in a["href"]:
                continue
            parts = [x.strip() for x in a.get_text("|", strip=True).split("|") if x.strip() and not BADGE.match(x.strip())]
            if "from" not in parts or len(parts) < 4:
                continue
            parts = parts[:parts.index("from")]
            m = next((i for i, x in enumerate(parts) if re.match(r"(Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*\.?,?\s+\d{1,2}\b", x)), None)
            if not m or m < 1:
                continue
            title = parts[m - 1]
            genre = parts[m - 2] if m >= 2 else ""
            out.append(row(title, theatre, parse_dates(" ".join(parts[m:])), absu("https://trafalgartickets.com", a["href"]), genre))
    return out


def _ld_date(s):
    if not s:
        return None
    s = str(s).strip()
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except ValueError:
        pass
    for f in ("%B %d, %Y %I:%M %p", "%B %d, %Y", "%d %B %Y"):
        try:
            return dt.datetime.strptime(s, f).date()
        except ValueError:
            pass
    return None


def read_jsonld(prefix, theatre, match=None, fallback_url=""):
    """Venues that publish schema.org Event data: one row per title, spanning its first to last date."""
    found = []
    for f in files(prefix):
        s = soup(f)
        for tag in (s.find_all("script", type="application/ld+json") if s else []):
            try:
                data = json.loads(tag.string or "")
            except ValueError:
                continue
            stack = [data]
            while stack:
                o = stack.pop()
                if isinstance(o, list):
                    stack.extend(o)
                elif isinstance(o, dict):
                    t = o.get("@type")
                    t = " ".join(t) if isinstance(t, list) else str(t)
                    if "Event" in t and o.get("name"):
                        found.append(o)
                    stack.extend(v for v in o.values() if isinstance(v, (list, dict)))
    groups = {}
    for o in found:
        loc = o.get("location")
        if match and isinstance(loc, dict) and loc.get("name") and match.lower() not in str(loc["name"]).lower():
            continue
        a = _ld_date(o.get("startDate"))
        b = _ld_date(o.get("endDate")) or a
        if not a:
            continue
        g = groups.setdefault(re.sub(r"\s+", " ", o["name"]).strip(), {"a": a, "b": b, "url": o.get("url") or ""})
        g["a"], g["b"] = min(g["a"], a), max(g["b"], b or a)
        g["url"] = g["url"] or o.get("url") or ""
    return [row(t, theatre, (g["a"], max(g["a"], g["b"])), g["url"] or fallback_url) for t, g in groups.items()]


for _v in _venue_files():
    if _v.get("reader") in ("lw", "trafalgar") and _v["name"] not in READERS:
        _fn = read_lw if _v["reader"] == "lw" else read_trafalgar
        READERS[_v["name"]] = (lambda f=_fn, s=_v["slug"], n=_v["name"], m=_v.get("match"): f(s, n, m) if f is read_lw else f(s, n))

for _v in _venue_files():
    if _v.get("reader") == "generic" and _v["name"] not in READERS:
        READERS[_v["name"]] = (lambda s=_v["slug"], n=_v["name"], u=_v["urls"][0], m=_v.get("match"): read_generic(s, n, u, m))

for _v in _venue_files():
    if _v.get("reader") == "jsonld" and _v["name"] not in READERS:
        READERS[_v["name"]] = (lambda s=_v["slug"], n=_v["name"], m=_v.get("match"), u=_v["urls"][0]: read_jsonld(s, n, m, u))


from urllib.parse import urljoin

DAY=r"(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*\.?,?\s*"
_DM = r"(?:"+DAY+r")?\d{1,2}(?:st|nd|rd|th)?\s+(?:"+MONTH_RE+r")[a-z]*\.?(?:\s*,?\s+20\d\d)?"
_MD = r"(?:"+DAY+r")?(?:"+MONTH_RE+r")[a-z]*\.?\s+\d{1,2}(?:st|nd|rd|th)?(?!\d)(?:\s*,?\s+20\d\d)?"
_DM0 = r"(?:"+DAY+r")?\d{1,2}(?:st|nd|rd|th)?(?:\s*(?:&|-|–|to)\s*(?:"+DAY+r")?\d{1,2}(?:st|nd|rd|th)?)?\s+(?:"+MONTH_RE+r")[a-z]*\.?(?:\s*,?\s+20\d\d)?"
DATE_RX=re.compile(r"(?:"+_DM0+r"(?:\s*(?:-|–|to)\s*"+_DM+r")?|"+_MD+r"(?:\s*(?:-|–|to)\s*"+_MD+r")?)",re.I)
NOISE=re.compile(r"^(show info|buy premium.*|contact our sales team|book tickets|contact us|buy now|enquire.*|(mon|tue|wed|thu|fri|sat|sun)[a-z]*\.?,?\s+\d{1,2}[:.]\d{2}.*|more times|\d+ more.*|up next|the|view all|see all|load more|show more|what.?s on|christmas|pantomime|panto|halloween|music|comedy|theatre|family|dance|talks?|film|musical|kids|children|classical|opera|ballet|events?|tickets? (&|and) info|tickets? & info|on sale.*|\d{1,2}[:.]\d{2}\s*(am|pm)?|sold out|low availability|selling fast|last tickets|few tickets left|new|on sale now|just announced|book now|buy tickets?|more info(rmation)?|find out more|view (event|show|details)|read more|tickets?|book|from|£.*|free|cancelled|postponed|moved|rescheduled|learn more|info|details|\d+|[|,-])$",re.I)
def card_for(el):
    c = el
    for _ in range(7):
        c = c.parent
        if c is None or c.name in ("body", "html", "main"):
            return None
        links = {a["href"] for a in c.find_all("a", href=True) if not a["href"].startswith(("#", "mailto", "tel", "javascript"))}
        if c.name == "a" and c.get("href"):
            links.add(c["href"])
        n = len(c.get_text(" ", strip=True))
        if links and 30 < n < 700:
            return c
    return None


def _jt(el):
    return re.sub(r"\s+,", ",", re.sub(r"\s+", " ", el.get_text(" ", strip=True)))


def read_generic(prefix, theatre, base, match=None):
    out, seen = [], set()
    for s in each(prefix):
        for tag in ("nav", "header", "footer", "script", "style"):
            for t in s.find_all(tag):
                t.decompose()
        for el in s.find_all(True):
            tx = _jt(el)
            if len(tx) > 90 or not DATE_RX.search(tx):
                continue
            if any(len(_jt(ch)) <= 90 and DATE_RX.search(_jt(ch)) for ch in el.find_all(True)):
                continue
            c = card_for(el)
            if c is None or id(c) in seen:
                continue
            seen.add(id(c))
            txt = c.get_text("|", strip=True)
            if match and match.lower() not in txt.lower():
                continue
            rng = parse_dates(DATE_RX.search(tx).group(0))
            if not rng:
                continue
            t = None
            for h in c.find_all(re.compile("^h[1-6]$")):
                tt = text(h)
                if tt and not DATE_RX.fullmatch(tt) and not NOISE.match(tt):
                    t = tt
                    break
            if not t:
                for p_ in [x.strip() for x in txt.split("|")]:
                    if p_ and not NOISE.match(p_) and not DATE_RX.search(p_) and len(p_) > 2:
                        t = p_
                        break
            if not t or len(t) < 4:
                continue
            href = None
            anc = c if c.name == "a" else c.find_parent("a", href=True)
            cand = ([anc] if anc else []) + c.find_all("a", href=True)
            for a_ in cand:
                h_ = a_["href"]
                if h_.startswith(("#", "mailto", "tel", "javascript")):
                    continue
                href = h_
                if text(a_) and not NOISE.match(text(a_)):
                    break
            if not href:
                continue
            if GENERIC_SKIP.search(t) or t.lower() in (theatre.lower(), (match or "").lower()):
                continue
            key = (t, rng)
            if key in seen:
                continue
            seen.add(key)
            out.append(row(t, theatre, rng, urljoin(base, href)))
    return merge_runs([r for r in out if r])


GENERIC_SKIP = re.compile(r"private (christmas )?part(y|ies)|workshop|backstage tour|building tour|heritage tour|\btours?\b|voucher|gift card|membership|\bhire\b|youth|\bclass(es)?\b|storytelling session|sensory stories|stay and play|rehearsal|private (hire|event)|open day|donat", re.I)


def merge_runs(rows):
    """Daily repeats of one title become a single listing spanning the run (gaps over 14 days stay separate)."""
    by = {}
    for r in rows:
        by.setdefault(r["title"].lower(), []).append(r)
    out = []
    for rs in by.values():
        rs.sort(key=lambda r: r["start"])
        cur = dict(rs[0])
        for r in rs[1:]:
            if (dt.date.fromisoformat(r["start"]) - dt.date.fromisoformat(cur["end"])).days <= 14:
                cur["end"] = max(cur["end"], r["end"])
            else:
                out.append(cur)
                cur = dict(r)
        out.append(cur)
    return out



def region_of(hit):
    """Group postcodes.io areas into the few regions shown on the site."""
    country, reg = hit.get("country") or "", hit.get("region") or ""
    if country in ("Scotland", "Wales"):
        return country
    if country == "Northern Ireland":
        return "Northern Ireland"
    if reg == "London":
        return "London"
    if reg in ("East Midlands", "West Midlands"):
        return "Midlands"
    if reg in ("North East", "North West", "Yorkshire and The Humber"):
        return "North"
    return "South & East"


def geocode_places():
    """Look up each configured venue's postcode (postcodes.io) so near-me search knows where it is."""
    import urllib.request
    todo = [v for v in _venue_files() if v.get("postcode")]
    places = {}
    for i in range(0, len(todo), 100):
        batch = todo[i:i + 100]
        try:
            req = urllib.request.Request("https://api.postcodes.io/postcodes", data=json.dumps({"postcodes": [v["postcode"] for v in batch]}).encode(), headers={"Content-Type": "application/json"})
            res = json.loads(urllib.request.urlopen(req, timeout=30).read())["result"]
        except Exception as e:
            print("geocode failed:", repr(e))
            continue
        for v, r in zip(batch, res):
            hit = r.get("result")
            if hit and hit.get("latitude"):
                places[v["name"]] = [v.get("city", ""), round(hit["latitude"], 4), round(hit["longitude"], 4), region_of(hit)]
    return places


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
    places = geocode_places()
    if places:
        data["places"] = places
    data["sample"] = False
    data["updated"] = dt.datetime.now(ZoneInfo("Europe/London")).isoformat(timespec="minutes")
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(merged)} shows written; venues not refreshed: {stale}")


if __name__ == "__main__":
    main()
