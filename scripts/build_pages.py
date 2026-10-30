"""Build static, search-friendly pages from shows.json.

Writes:
  venues/<slug>/index.html      one page per venue with current shows
  cities/<slug>/index.html      one page per city
  categories/<slug>/index.html  comedy, pantomime, musicals ...
  venues/index.html, cities/index.html, categories/index.html   hub pages
  assets/pages.css
  sitemap.xml

Everything generated is wiped and rebuilt on each run, so pages for venues
with no current shows disappear instead of going stale.
"""
import html
import json
import re
import shutil
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from urllib.parse import quote, unquote, urlparse, parse_qs

ROOT = Path(__file__).resolve().parent.parent
SITE = "https://findashow.co.uk"
AFF_BASE = "https://ticketmaster.evyy.net/c/8068961/264167/4272"
AFF_PROP = "9082472"
GEN_DIRS = ["venues", "cities", "categories"]

# Raw genre labels from the venue sites -> a tidy category page.
CATEGORIES = {
    "comedy": ("Comedy", "Comedy", {"comedy"}),
    "pantomime": ("Pantomime", "Pantomime", {"pantomime"}),
    "musicals": ("Musicals", "Musical", {"musical", "musicals"}),
    "christmas": ("Christmas shows", "Christmas", {"christmas"}),
    "tribute-acts": ("Tribute acts", "Tribute", {"tribute"}),
    "classical": ("Classical and orchestral", "Classical", {"classical"}),
    "family": ("Family shows", "Family", {"family"}),
    "concerts": ("Concerts and live music", "Music", {"music", "concert", "concerts"}),
}

CSS = """
:root{--bg:#faf6ef;--surface:#fff;--surface-2:#f1eadf;--line:#ded3c2;--fg:#1f1a16;--muted:#6a5f54;--accent:#e4572e;--accent-fg:#fff;--rose:#b8185a;
--font-display:"Bebas Neue","Oswald","Arial Narrow",Impact,sans-serif;--font-body:"Hanken Grotesk","Helvetica Neue",Arial,sans-serif;--font-small:"Barlow Condensed","Arial Narrow",Arial,sans-serif;color-scheme:light}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 var(--font-body);-webkit-text-size-adjust:100%}
a{color:var(--rose)}
.wrap{max-width:860px;margin:0 auto;padding:0 16px 56px}
.top{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:18px 0 6px}
.brand{font-family:var(--font-display);font-size:26px;letter-spacing:.06em;color:var(--fg);text-decoration:none}
.brand b{color:var(--accent);font-weight:400}
.top a.home{font-family:var(--font-small);font-weight:600;font-size:15px;letter-spacing:.1em;text-transform:uppercase;text-decoration:none;color:var(--fg);border:1.5px solid var(--fg);padding:7px 12px;border-radius:999px}
.crumbs{font-size:14px;color:var(--muted);margin:14px 0 0}
.crumbs a{color:var(--muted)}
h1{margin:6px 0 0;font-family:var(--font-display);font-weight:400;font-size:clamp(38px,8vw,62px);line-height:.98;letter-spacing:.015em;text-wrap:balance}
.lede{color:var(--muted);margin:10px 0 0;max-width:62ch}
h2{margin:30px 0 8px;font-family:var(--font-display);font-weight:400;font-size:28px;letter-spacing:.08em;color:var(--accent)}
h2 a{color:inherit;text-decoration:none}
.card{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:14px 16px;margin:10px 0;display:flex;gap:14px;align-items:center;justify-content:space-between;flex-wrap:wrap}
.card h3{margin:0;font-size:18px;line-height:1.25}
.meta{margin:2px 0 0;color:var(--muted);font-size:14px}
.act{display:flex;gap:8px;flex-wrap:wrap}
.btn{display:inline-block;font-family:var(--font-small);font-weight:600;font-size:15px;letter-spacing:.08em;text-transform:uppercase;text-decoration:none;padding:8px 14px;border-radius:999px;background:var(--accent);color:var(--accent-fg)}
.btn.ghost{background:transparent;color:var(--fg);border:1.5px solid var(--fg)}
.cta{margin:28px 0 0;padding:16px;border-radius:14px;background:var(--surface-2);border:1px solid var(--line)}
.cta p{margin:0 0 10px}
.chips{display:flex;flex-wrap:wrap;gap:8px;list-style:none;margin:8px 0 0;padding:0}
.chips a{display:inline-block;padding:6px 12px;border:1px solid var(--line);border-radius:999px;background:var(--surface);color:var(--fg);text-decoration:none;font-size:14px}
.chips a:hover{border-color:var(--accent)}
.chips small{color:var(--muted)}
.note{font-size:13px;color:var(--muted);margin-top:26px}
footer{margin-top:36px;padding-top:16px;border-top:1px solid var(--line);font-size:14px;color:var(--muted)}
footer a{color:var(--muted)}
"""


# Venues that have no geocoded city in shows.json.
EXTRA_CITY = {"King's Theatre Glasgow": "Glasgow", "O2 Academy Leeds": "Leeds", "Watford Colosseum": "Watford"}


def midlands_places():
    """Midlands venues keep their city in the PLACE table inside index.html."""
    src = (ROOT / "index.html").read_text(encoding="utf-8")
    out = {}
    for m in re.finditer(r'"([^"]+)":\s*\["[^"]*",\s*"([^"]+)",\s*(-?[\d.]+),\s*(-?[\d.]+)\]', src):
        city = m.group(2).split(",")[-1].strip()
        out[m.group(1)] = [city, float(m.group(3)), float(m.group(4)), "Midlands"]
    return out


def slug(s):
    s = s.lower().replace("&", " and ").replace("'", "").replace("’", "")
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-") or "x"


def esc(s):
    return html.escape(str(s), quote=True)


def d(s):
    return datetime.strptime(s, "%Y-%m-%d").date()


def fmt(x, year=True):
    return f"{x.day} {x.strftime('%b')}" + (f" {x.year}" if year else "")


def dates_text(s, today):
    a, b = d(s["start"]), d(s["end"])
    if a == b:
        return f"{x_day(a)} {fmt(a)}"
    if a <= today:
        return f"On now, until {fmt(b)}"
    if a.year == b.year:
        return f"{fmt(a, False)} to {fmt(b)}"
    return f"{fmt(a)} to {fmt(b)}"


def x_day(a):
    return a.strftime("%a")


def tm_link(url):
    """Our own affiliate wrap around a plain ticketmaster.co.uk page."""
    if not url:
        return ""
    try:
        page = url
        u = urlparse(url)
        if re.search(r"(^|\.)evyy\.net$", u.hostname or "") and parse_qs(u.query).get("u"):
            page = parse_qs(u.query)["u"][0]
        if not re.search(r"(^|\.)ticketmaster\.co\.uk$", urlparse(page).hostname or ""):
            return ""
    except Exception:
        return ""
    return f"{AFF_BASE}?u={quote(page, safe='')}&partnerpropertyid={AFF_PROP}"


def plural(n, word):
    return f"{n} {word}{'' if n == 1 else 's'}"


def page(title, desc, path, body, ld=None):
    url = f"{SITE}{path}"
    ldtag = ""
    if ld:
        ldtag = '<script type="application/ld+json">' + json.dumps(ld, ensure_ascii=False).replace("</", "<\\/") + "</script>"
    return f"""<!doctype html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<meta name="theme-color" content="#faf6ef">
<link rel="canonical" href="{url}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="Find a Show">
<meta property="og:locale" content="en_GB">
<meta property="og:url" content="{url}">
<meta property="og:image" content="{SITE}/og.png">
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" href="/og.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Barlow+Condensed:wght@500;600&family=Hanken+Grotesk:wght@400;500;600;700&display=swap">
<link rel="stylesheet" href="/assets/pages.css">
{ldtag}
</head>
<body>
<div class="wrap">
<div class="top"><a class="brand" href="/">Find a <b>Show</b></a><a class="home" href="/">Search all shows</a></div>
{body}
<footer>
<a href="/">Find a Show</a> &middot; <a href="/cities/">Cities</a> &middot; <a href="/venues/">Venues</a> &middot; <a href="/categories/">Categories</a>
<p>Find a Show is an independent guide and is not run by any venue. Dates come from the venues' own websites and can change, so check with the venue before you travel.
Some ticket links are affiliate links, which means we may earn a commission if you buy, at no extra cost to you.</p>
</footer>
</div>
</body>
</html>
"""


def show_card(s, today, show_venue=False, show_city=None):
    meta = dates_text(s, today)
    if show_venue:
        meta = f"{esc(s['theatre'])}" + (f", {esc(show_city)}" if show_city else "") + f" &middot; {esc(meta)}"
    else:
        meta = esc(meta)
    acts = f'<a class="btn" href="{esc(s["url"])}" target="_blank" rel="noopener noreferrer">View show</a>' if s.get("url") else ""
    tm = tm_link(s.get("tm"))
    if tm:
        acts += f' <a class="btn ghost" href="{esc(tm)}" target="_blank" rel="sponsored noopener noreferrer">Buy on Ticketmaster</a>'
    return f'<div class="card"><div><h3>{esc(s["title"])}</h3><p class="meta">{meta}</p></div><div class="act">{acts}</div></div>'


def events_ld(shows, places, today, limit=60):
    items = []
    for s in shows[:limit]:
        city = (places.get(s["theatre"]) or [None])[0]
        loc = {"@type": "Place", "name": s["theatre"]}
        if city:
            loc["address"] = {"@type": "PostalAddress", "addressLocality": city, "addressCountry": "GB"}
        ev = {
            "@type": "Event",
            "name": s["title"],
            "startDate": max(d(s["start"]), today).isoformat(),
            "endDate": s["end"],
            "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode",
            "location": loc,
        }
        if s.get("url"):
            ev["url"] = s["url"]
        items.append(ev)
    return {"@context": "https://schema.org", "@graph": items}


def sort_key(today):
    return lambda s: (max(d(s["start"]), today), s["title"].lower())


def write(path, text):
    p = ROOT / path.strip("/") / "index.html"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def chips(items):
    return '<ul class="chips">' + "".join(
        f'<li><a href="{esc(h)}">{esc(t)} <small>{esc(n)}</small></a></li>' for h, t, n in items) + "</ul>"


def main():
    data = json.loads((ROOT / "shows.json").read_text(encoding="utf-8"))
    places = dict(data.get("places", {}))
    for k, v in midlands_places().items():
        places.setdefault(k, v)
    for k, c in EXTRA_CITY.items():
        places.setdefault(k, [c, None, None, ""])
    today = date.today()
    shows = [s for s in data["shows"] if s.get("title") and s.get("theatre") and s.get("start") and s.get("end") and d(s["end"]) >= today]
    shows.sort(key=sort_key(today))

    for g in GEN_DIRS:
        shutil.rmtree(ROOT / g, ignore_errors=True)
    (ROOT / "assets").mkdir(exist_ok=True)
    (ROOT / "assets" / "pages.css").write_text(CSS.strip() + "\n", encoding="utf-8")

    by_venue = defaultdict(list)
    for s in shows:
        by_venue[s["theatre"]].append(s)

    # Unique slugs per venue (add the city if two venues share a name).
    vslug, used = {}, set()
    for v in sorted(by_venue):
        city = (places.get(v) or [None])[0]
        sl = slug(v)
        if sl in used and city:
            sl = slug(f"{v} {city}")
        n, base = 2, sl
        while sl in used:
            sl, n = f"{base}-{n}", n + 1
        used.add(sl)
        vslug[v] = sl

    by_city = defaultdict(list)
    for v, lst in by_venue.items():
        city = (places.get(v) or [None])[0]
        if city:
            by_city[city].extend(lst)
    cslug = {c: slug(c) for c in by_city}

    urls = [("/", "daily")]
    updated = data.get("updated", "")[:10]

    # ---- venue pages
    for v, lst in by_venue.items():
        city = (places.get(v) or [None])[0]
        region = (places.get(v) or [None, None, None, None])[3]
        path = f"/venues/{vslug[v]}/"
        where = f"{v}, {city}" if city else v
        n = len(lst)
        crumbs = '<p class="crumbs"><a href="/">Home</a> / <a href="/venues/">Venues</a>' + (
            f' / <a href="/cities/{cslug[city]}/">{esc(city)}</a>' if city else "") + "</p>"
        others = ""
        if city:
            sib = sorted(x for x in {s["theatre"] for s in by_city[city]} if x != v)
            if sib:
                others = f"<h2>Other venues in {esc(city)}</h2>" + chips(
                    (f"/venues/{vslug[x]}/", x, len(by_venue[x])) for x in sib)
        cards = "".join(show_card(s, today) for s in lst)
        body = f"""{crumbs}
<h1>What's on at {esc(v)}</h1>
<p class="lede">{plural(n, 'show')} currently listed at {esc(where)}. Dates are taken from the venue's own website and refreshed every day.</p>
<h2>Shows and dates</h2>
{cards}
<div class="cta"><p>Looking for something else{(' in ' + esc(city)) if city else ''}? Search every show and venue in one place.</p><a class="btn" href="/">Search all shows</a></div>
{others}"""
        title = f"What's on at {v}{', ' + city if city else ''} | Find a Show"
        desc = f"{plural(n, 'show')} at {where}: dates and links to book. Updated daily on Find a Show."
        write(path, page(title, desc, path, body, events_ld(lst, places, today)))
        urls.append((path, "daily"))

    # ---- city pages
    for city, lst in by_city.items():
        lst = sorted(lst, key=sort_key(today))
        path = f"/cities/{cslug[city]}/"
        vs = sorted({s["theatre"] for s in lst})
        sections = ""
        for v in vs:
            sub = [s for s in lst if s["theatre"] == v]
            sections += f'<h2><a href="/venues/{vslug[v]}/">{esc(v)}</a></h2>' + "".join(show_card(s, today) for s in sub)
        body = f"""<p class="crumbs"><a href="/">Home</a> / <a href="/cities/">Cities</a></p>
<h1>What's on in {esc(city)}</h1>
<p class="lede">{plural(len(lst), 'show')} across {plural(len(vs), 'venue')} in {esc(city)}, including theatre, comedy, music and more. Refreshed daily from the venues' own websites.</p>
<h2>Venues in {esc(city)}</h2>
{chips((f"/venues/{vslug[v]}/", v, len([s for s in lst if s['theatre'] == v])) for v in vs)}
{sections}
<div class="cta"><p>Want to filter by date or type of show?</p><a class="btn" href="/">Search all shows</a></div>"""
        title = f"What's on in {city}: live shows, theatre, comedy and music | Find a Show"
        desc = f"{plural(len(lst), 'live show')} at {plural(len(vs), 'venue')} in {city}. See dates and book tickets."
        write(path, page(title, desc, path, body, events_ld(lst, places, today)))
        urls.append((path, "daily"))

    # ---- category pages
    cats = []
    for key, (label, _g, raw) in CATEGORIES.items():
        lst = [s for s in shows if (s.get("genre") or "").strip().lower() in raw]
        if len(lst) < 5:
            continue
        path = f"/categories/{key}/"
        shown = lst[:150]
        cards = "".join(show_card(s, today, True, (places.get(s["theatre"]) or [None])[0]) for s in shown)
        more = f'<p class="note">Showing the first {len(shown)} of {len(lst)}. <a href="/">Search all shows</a> to see the rest.</p>' if len(lst) > len(shown) else ""
        body = f"""<p class="crumbs"><a href="/">Home</a> / <a href="/categories/">Categories</a></p>
<h1>{esc(label)} across the UK</h1>
<p class="lede">{plural(len(lst), 'listing')} at venues around the UK, in date order. Refreshed daily.</p>
{cards}{more}
<div class="cta"><p>Filter by city and date on the main search.</p><a class="btn" href="/">Search all shows</a></div>"""
        title = f"{label} across the UK: dates and tickets | Find a Show"
        desc = f"{label} at UK venues: {plural(len(lst), 'listing')} with dates and links to book. Updated daily."
        write(path, page(title, desc, path, body, events_ld(shown, places, today)))
        urls.append((path, "daily"))
        cats.append((f"/categories/{key}/", label, len(lst)))

    # ---- hubs
    cities = sorted(by_city)
    write("/cities/", page("Live shows by city | Find a Show", "Browse what's on in cities across the UK.", "/cities/",
        '<p class="crumbs"><a href="/">Home</a></p><h1>Live shows by city</h1><p class="lede">Pick a city to see what is on at its venues.</p>'
        + chips((f"/cities/{cslug[c]}/", c, len(by_city[c])) for c in cities)))
    urls.append(("/cities/", "daily"))
    write("/venues/", page("Venues across the UK | Find a Show", "Browse UK theatres, arenas and venues and see what is on.", "/venues/",
        '<p class="crumbs"><a href="/">Home</a></p><h1>Venues across the UK</h1><p class="lede">Every venue we cover that has shows listed right now.</p>'
        + chips((f"/venues/{vslug[v]}/", v, len(by_venue[v])) for v in sorted(by_venue))))
    urls.append(("/venues/", "daily"))
    write("/categories/", page("Browse shows by type | Find a Show", "Comedy, pantomime, musicals, concerts and more across the UK.", "/categories/",
        '<p class="crumbs"><a href="/">Home</a></p><h1>Browse shows by type</h1><p class="lede">Pick a type of show.</p>' + chips(cats)))
    urls.append(("/categories/", "daily"))

    # ---- sitemap
    lm = updated or today.isoformat()
    xml = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for p, freq in urls:
        xml.append(f"<url><loc>{SITE}{p}</loc><lastmod>{lm}</lastmod><changefreq>{freq}</changefreq></url>")
    xml.append("</urlset>")
    (ROOT / "sitemap.xml").write_text("\n".join(xml) + "\n", encoding="utf-8")

    print(f"Built {len(by_venue)} venue pages, {len(by_city)} city pages, {len(cats)} category pages, {len(urls)} URLs in sitemap")


if __name__ == "__main__":
    main()
