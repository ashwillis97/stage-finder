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
GEN_DIRS = ["west-end-shows", "venues", "cities", "categories", "pantomime", "christmas-shows", "new"]

# Raw genre labels from the venue sites -> a tidy category page.
CATEGORIES = {
    "comedy": ("Comedy", "Comedy", {"comedy"}),
    "musicals": ("Musicals", "Musical", {"musical", "musicals"}),
    "tribute-acts": ("Tribute acts", "Tribute", {"tribute"}),
    "classical": ("Classical and orchestral", "Classical", {"classical"}),
    "family": ("Family and kids shows", "Family", {"family"}),
    "concerts": ("Concerts and live music", "Music", {"music", "concert", "concerts"}),
}

WEST_END = {"Adelphi Theatre","London Palladium","Dominion Theatre","Theatre Royal Drury Lane","Apollo Theatre","Prince Edward Theatre","Wyndham's Theatre","Noël Coward Theatre","Criterion Theatre","Vaudeville Theatre","St Martin's Theatre","Ambassadors Theatre","Palace Theatre","Playhouse Theatre","Sondheim Theatre","Novello Theatre","Gielgud Theatre","His Majesty's Theatre","Duke of York's Theatre","Phoenix Theatre","Prince of Wales Theatre","Apollo Victoria Theatre","Trafalgar Theatre","Garrick Theatre","Harold Pinter Theatre","Savoy Theatre","Piccadilly Theatre","London Coliseum","Peacock Theatre","Aldwych Theatre","Cambridge Theatre","Gillian Lynne Theatre","Lyceum Theatre","Victoria Palace Theatre","Fortune Theatre","Shaftesbury Theatre","Theatre Royal Haymarket","Sadler's Wells Theatre","The Old Vic"}

CSS = """
:root{--bg:#faf6ef;--surface:#fff;--surface-2:#f1eadf;--line:#ded3c2;--fg:#1f1a16;--muted:#6a5f54;--accent:#e4572e;--accent-fg:#fff;--rose:#b8185a;
--font-display:"Outfit","Helvetica Neue",Arial,sans-serif;--font-body:"Outfit","Helvetica Neue",Arial,sans-serif;--font-small:"Outfit","Helvetica Neue",Arial,sans-serif;color-scheme:light}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 var(--font-body);-webkit-text-size-adjust:100%}
a{color:var(--rose)}
.wrap{max-width:860px;margin:0 auto;padding:0 16px 56px}
.top{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:18px 0 6px}
.brand{font-family:var(--font-display);font-weight:800;font-size:26px;letter-spacing:-.02em;color:var(--fg);text-decoration:none}
.brand b{color:var(--accent);font-weight:400}
.top a.home{font-family:var(--font-small);font-weight:600;font-size:15px;letter-spacing:.06em;text-transform:uppercase;text-decoration:none;color:var(--fg);border:0;border-bottom:1.5px solid var(--fg);padding:2px 0;border-radius:0}
.crumbs{font-size:14px;color:var(--muted);margin:14px 0 0}
.crumbs a{color:var(--muted)}
h1{margin:6px 0 0;font-family:var(--font-display);font-weight:800;font-size:clamp(34px,7vw,54px);line-height:1.05;letter-spacing:-.03em;text-wrap:balance}
.lede{color:var(--muted);margin:10px 0 0;max-width:62ch}
h2{margin:30px 0 8px;font-family:var(--font-display);font-weight:700;font-size:22px;letter-spacing:-.01em;color:var(--accent)}
h2 a{color:inherit;text-decoration:none}
.card{padding:16px 0;margin:0;border-bottom:1px solid var(--line);display:grid;grid-template-columns:minmax(0,1fr) auto;gap:14px;align-items:center}
.card .act{flex-wrap:nowrap;justify-content:flex-end}
.card .btn{background:none;border:0;border-radius:0;min-height:0;padding:0;color:#a8391a;font-weight:600;font-size:15px;min-width:0}
.card .btn::after{content:" \\2192"}
.card .btn:hover{text-decoration:underline}
.btn{white-space:nowrap;text-align:center}
@media(max-width:560px){.card{grid-template-columns:1fr}.card .act{justify-content:flex-start}}
.card h3{margin:0;font-size:19px;font-weight:700;line-height:1.25;letter-spacing:-.01em}
.meta{margin:2px 0 0;color:var(--muted);font-size:14px}
.act{display:flex;gap:8px;flex-wrap:wrap}
.btn{display:inline-block;font-family:var(--font-small);font-weight:600;font-size:15px;letter-spacing:0;text-transform:none;text-decoration:underline;text-underline-offset:3px;padding:0;border-radius:0;background:none;color:#a8391a}
.btn.ghost{background:transparent;color:var(--fg);border:1.5px solid var(--fg)}
.cta{margin:28px 0 0;padding:20px 0 0;border-top:1.5px solid var(--fg)}
.cta p{margin:0 0 10px}
.chips{display:flex;flex-wrap:wrap;gap:6px 22px;list-style:none;margin:8px 0 0;padding:0}
.chips a{display:inline-block;padding:2px 0;border:0;background:none;color:var(--fg);text-decoration:none;font-size:15px;font-weight:500}
.chips a:hover{color:#a8391a;text-decoration:underline}
.chips small{color:var(--muted)}
.note{font-size:13px;color:var(--muted);margin-top:26px}
footer{margin-top:36px;padding-top:16px;border-top:1px solid var(--line);font-size:14px;color:var(--muted)}
footer a{color:var(--muted)}
.faq h3{margin:20px 0 4px;font-size:17px}
.faq p{margin:0;color:var(--muted)}
.alerts{display:flex;gap:32px;align-items:center;margin:36px 0 0;padding:24px;background:var(--surface-2);border:1px solid var(--line);border-radius:16px}
.alerts-text{flex:1;min-width:0}
.alerts h2{margin:0;font-size:22px;font-weight:700;color:var(--fg)}
.alerts-text p{margin:6px 0 0;color:var(--muted);font-size:15px;line-height:1.4}
.alerts form{flex:1.2;min-width:0}
.alerts label{display:block;margin-bottom:4px;font-size:13px;color:var(--muted)}
.alerts-row{display:flex;gap:12px}
.alerts-row input[type=email]{flex:1;min-width:0;min-height:44px;padding:0 14px;font:inherit;font-size:16px;border:1px solid rgba(31,26,22,.18);border-radius:12px;background:#fff;color:var(--fg)}
.alerts-btn{min-height:44px;padding:0 20px;border:0;border-radius:10px;background:var(--accent);color:#fff;font:inherit;font-weight:600;font-size:15px;cursor:pointer}
.alerts-note{margin:10px 0 0;font-size:13px;color:var(--muted)}
.alerts-note.ok{color:#1f6b3a;font-weight:600}.alerts-note.bad{color:#a8391a}
.top .alertlink{margin-left:auto;margin-right:16px;font-size:14px;color:var(--muted)}
@media(max-width:700px){.alerts{flex-direction:column;align-items:stretch;gap:16px;padding:20px}.alerts form{flex:none}.top .alertlink{display:none}}
.intro{margin:14px 0 0;max-width:68ch}
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


PANTO_TITLE = re.compile(r"\b(cinderella|aladdin|peter pan|jack and the beanstalk|snow white|sleeping beauty|dick whittington|mother goose|beauty and the beast|robin hood|puss in boots|goldilocks|babes in the wood|pinocchio|wizard of oz|little mermaid|panto|pantomime)\b", re.I)
NOT_PANTO = re.compile(r"ballet|bourne|rehearsal|set tour|\btalk\b|mixer|workshop|\bjr\b|opera|\bice\b|concert|dance|jazz|school|youth|junior|livestream|easter", re.I)
XMAS_TITLE = re.compile(r"\b(christmas|xmas|festive|nativity|nutcracker|carols|scrooge|snowman|grinch|polar express|winter wonderland|elf)\b", re.I)
NOT_XMAS = re.compile(r"part(y|ies)|shopping|fayre|livestream|primary school|wassail|afternoon tea|gift fair|good food|market|paint|dining|dinner|disco|workshop", re.I)

SEASONS = {
    "pantomime": {
        "label": "Pantomime", "one": "pantomime", "many": "pantomimes", "min_city": 2, "other": "christmas-shows",
        "faq": [
            ("When does pantomime season start?", "Most pantomimes open in late November or early December and run until early January. Some start earlier and a few run into February, so check the dates for each show."),
            ("How do I find a pantomime near me?", "Pick your city from the list on this page, or use the search and Where filter on the Find a Show homepage to see pantomimes at venues near you."),
            ("Are there relaxed or accessible performances?", "Many venues add relaxed, signed or accessible performances to their pantomime run. They usually appear as separate listings or on the show's own page, so check with the venue."),
            ("How do I book tickets?", "Use the button on each listing. It takes you to the venue or its ticket partner, where you can pick a date and seats."),
        ],
    },
    "christmas-shows": {
        "label": "Christmas shows", "one": "Christmas show", "many": "Christmas shows", "min_city": 3, "other": "pantomime",
        "faq": [
            ("What kinds of Christmas shows are there?", "Carol and choral concerts, Christmas musicals, festive comedy, ballet, family shows and tribute acts all appear here, alongside well-known stories such as A Christmas Carol."),
            ("How do I find Christmas shows near me?", "Pick your city from the list on this page, or use the search and Where filter on the Find a Show homepage."),
            ("When should I book?", "Popular Christmas dates, especially weekends in December, can sell out. If a date you want is available, booking early is the safest option."),
            ("Where do the dates come from?", "Dates are taken from each venue's own website and refreshed every day. Always check with the venue before you travel."),
        ],
    },
}


def season_year(today):
    return today.year if today.month >= 6 else today.year - 1


def is_panto(s, y):
    if NOT_PANTO.search(s["title"]):
        return False
    if (s.get("genre") or "").strip().lower() == "pantomime":
        return True
    a, b = d(s["start"]), d(s["end"])
    return bool(PANTO_TITLE.search(s["title"])) and (b - a).days <= 75 and a <= date(y + 1, 1, 31) and b >= date(y, 11, 15)


def is_xmas(s, y):
    if is_panto(s, y) or NOT_XMAS.search(s["title"]):
        return False
    a = d(s["start"])
    return ((s.get("genre") or "").strip().lower() == "christmas" or bool(XMAS_TITLE.search(s["title"]))) and a <= date(y, 12, 31)


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


ALERTS = """<section class="alerts" id="alerts" aria-labelledby="alertsTitle">
<div class="alerts-text"><h2 id="alertsTitle">Get new shows by email</h2><p>One email a week with shows added across the UK. Unsubscribe whenever you like.</p></div>
<form id="alertsForm" action="https://assets.mailerlite.com/jsonp/2760636/forms/202963478294562355/subscribe" method="post" target="_blank">
<label for="alertsEmail">Email</label>
<div class="alerts-row"><input id="alertsEmail" type="email" name="fields[email]" placeholder="you@example.com" autocomplete="email" required><input type="hidden" name="ml-submit" value="1"><input type="hidden" name="anticsrf" value="true"><button class="alerts-btn" type="submit">Sign up</button></div>
<p class="alerts-note" id="alertsNote">We'll send a confirmation email first. Your address is only used for these emails.</p>
</form></section>
<script>(function(){var f=document.getElementById("alertsForm");if(!f)return;var n=document.getElementById("alertsNote"),b=f.querySelector("button");f.addEventListener("submit",function(e){e.preventDefault();var m=f.elements["fields[email]"].value.trim();if(!m)return;b.disabled=true;b.textContent="Signing up";fetch(f.action,{method:"POST",mode:"no-cors",body:new URLSearchParams({"fields[email]":m,"ml-submit":"1","anticsrf":"true"})}).then(function(){f.elements["fields[email]"].value="";n.className="alerts-note ok";n.textContent="Thanks. Check your inbox and click the link in our confirmation email to finish signing up.";b.textContent="Sign up";b.disabled=false}).catch(function(){n.className="alerts-note bad";n.textContent="That didn't go through. Please try again in a moment.";b.textContent="Sign up";b.disabled=false})})})();</script>
"""


def page(title, desc, path, body, ld=None, noindex=False):
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
{'<meta name="robots" content="noindex">' if noindex else ""}
<link rel="canonical" href="{url}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="Find a Show">
<meta property="og:locale" content="en_GB">
<meta property="og:url" content="{url}">
<meta property="og:image" content="{SITE}/og.png">
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" href="/favicon.ico" sizes="48x48">
<link rel="icon" type="image/svg+xml" href="/assets/favicon.svg">
<link rel="icon" type="image/png" sizes="192x192" href="/assets/favicon-192.png">
<link rel="apple-touch-icon" href="/assets/apple-touch-icon.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700;800&display=swap">
<link rel="stylesheet" href="/assets/pages.css">
{ldtag}
</head>
<body>
<div class="wrap">
<div class="top"><a class="brand" href="/">Find a <b>Show</b></a><a class="alertlink" href="#alerts">Email alerts</a><a class="home" href="/">Search all shows</a></div>
{body}
{ALERTS}<footer>
<a href="/">Find a Show</a> &middot; <a href="/cities/">Cities</a> &middot; <a href="/venues/">Venues</a> &middot; <a href="/categories/">Categories</a>
<p>Find a Show is an independent guide and is not run by any venue. Dates come from the venues' own websites and can change, so check with the venue before you travel.
Some ticket links are affiliate links, which means we may earn a commission if you buy, at no extra cost to you.</p>
</footer>
</div>
<script defer src='https://static.cloudflareinsights.com/beacon.min.js' data-cf-beacon='{{"token": "8386717571e94d43ae043733aa4dc407"}}'></script>
</body>
</html>
"""


def show_card(s, today, show_venue=False, show_city=None):
    meta = dates_text(s, today)
    if show_venue:
        meta = f"{esc(s['theatre'])}" + (f", {esc(show_city)}" if show_city else "") + f" &middot; {esc(meta)}"
    else:
        meta = esc(meta)
    tm = tm_link(s.get("tm"))
    if tm:
        acts = f'<a class="btn" href="{esc(tm)}" target="_blank" rel="sponsored noopener noreferrer">Buy on Ticketmaster</a>'
    elif s.get("url"):
        acts = f'<a class="btn" href="{esc(s["url"])}" target="_blank" rel="noopener noreferrer">Tickets &amp; info</a>'
    else:
        acts = ""
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
            "description": f"{s['title']} at {s['theatre']}" + (f", {city}" if city else "") + ". Dates and tickets via Find a Show.",
            "startDate": s["start"],
            "endDate": s["end"],
            "eventStatus": "https://schema.org/EventScheduled",
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
    sy = season_year(today)
    seasonal = {}
    for key, cfg in SEASONS.items():
        pick = is_panto if key == "pantomime" else is_xmas
        lst = [s for s in shows if pick(s, sy)]
        bc = defaultdict(list)
        for s in lst:
            c = (places.get(s["theatre"]) or [None])[0]
            if c:
                bc[c].append(s)
        seasonal[key] = {"cfg": cfg, "shows": lst, "by_city": bc, "cities": {c for c, v in bc.items() if len(v) >= cfg["min_city"]}}

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
    catcity = {}
    for key, (label, _g, raw) in CATEGORIES.items():
        bcc = defaultdict(list)
        for s in shows:
            if (s.get("genre") or "").strip().lower() in raw:
                c = (places.get(s["theatre"]) or [None])[0]
                if c:
                    bcc[c].append(s)
        catcity[key] = {c: v for c, v in bcc.items() if len(v) >= 5}

    def catcity_links(c):
        items = [(f"/categories/{k}/{slug(c)}/", f"{CATEGORIES[k][0]} in {c}", len(v[c])) for k, v in catcity.items() if c in v]
        return ("<h2>By type</h2>" + chips(items)) if items else ""

    for city, lst in by_city.items():
        lst = sorted(lst, key=sort_key(today))
        path = f"/cities/{cslug[city]}/"
        def seasonal_links(c):
            items = [(f"/{k}/{slug(c)}/", f"{v['cfg']['label']} in {c}", len(v['by_city'][c])) for k, v in seasonal.items() if c in v["cities"]]
            return ("<h2>Seasonal</h2>" + chips(items)) if items else ""

        vs = sorted({s["theatre"] for s in lst})
        sections = ""
        for v in vs:
            sub = [s for s in lst if s["theatre"] == v]
            sections += f'<h2><a href="/venues/{vslug[v]}/">{esc(v)}</a></h2>' + "".join(show_card(s, today) for s in sub)
        body = f"""<p class="crumbs"><a href="/">Home</a> / <a href="/cities/">Cities</a></p>
<h1>Shows in {esc(city)}: what's on</h1>
<p class="lede">{plural(len(lst), 'show')} across {plural(len(vs), 'venue')} in {esc(city)}, including theatre, comedy, music and more. Refreshed daily from the venues' own websites.</p>
<h2>Venues in {esc(city)}</h2>
{chips((f"/venues/{vslug[v]}/", v, len([s for s in lst if s['theatre'] == v])) for v in vs)}
{seasonal_links(city)}
{catcity_links(city)}
{sections}
<div class="cta"><p>Want to filter by date or type of show?</p><a class="btn" href="/">Search all shows</a></div>"""
        title = (f"Shows in London: West End, theatre, comedy and music | Find a Show" if city == "London" else f"Shows in {city}: what's on, theatre, comedy and music | Find a Show")
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
        bycity = ("<h2>By city</h2>" + chips((f"/categories/{key}/{slug(c)}/", c, len(v)) for c, v in sorted(catcity.get(key, {}).items()))) if catcity.get(key) else ""
        more = f'<p class="note">Showing the first {len(shown)} of {len(lst)}. <a href="/">Search all shows</a> to see the rest.</p>' if len(lst) > len(shown) else ""
        body = f"""<p class="crumbs"><a href="/">Home</a> / <a href="/categories/">Categories</a></p>
<h1>{esc(label)} across the UK</h1>
<p class="lede">{plural(len(lst), 'listing')} at venues around the UK, in date order. Refreshed daily.</p>
{bycity}
{cards}{more}
<div class="cta"><p>Filter by city and date on the main search.</p><a class="btn" href="/">Search all shows</a></div>"""
        title = f"{label} across the UK: dates and tickets | Find a Show"
        desc = f"{label} at UK venues: {plural(len(lst), 'listing')} with dates and links to book. Updated daily."
        write(path, page(title, desc, path, body, events_ld(shown, places, today)))
        urls.append((path, "daily"))
        cats.append((f"/categories/{key}/", label, len(lst)))
        cc = catcity.get(key, {})
        for c, cl in sorted(cc.items()):
            cpath = f"/categories/{key}/{slug(c)}/"
            cv = len({s["theatre"] for s in cl})
            kids = " (kids and family)" if key == "family" else ""
            h1 = f"Kids and family shows in {c}" if key == "family" else f"{label} in {c}"
            cbody = f"""<p class="crumbs"><a href="/">Home</a> / <a href="/categories/{key}/">{esc(label)}</a> / {esc(c)}</p>
<h1>{esc(h1)}</h1>
<p class="lede">{plural(len(cl), 'listing')} at {plural(cv, 'venue')} in {esc(c)}, in date order. Dates come from each venue's own website and are refreshed daily.</p>
{"".join(show_card(s, today, True, c) for s in cl[:150])}
<div class="cta"><p>See {esc(label.lower())} <a href="/categories/{key}/">across the UK</a>, everything on in <a href="/cities/{slug(c)}/">{esc(c)}</a>, or search every show.</p><a class="btn" href="/">Search all shows</a></div>"""
            write(cpath, page(f"{h1}: dates and tickets | Find a Show", f"{h1}: {plural(len(cl), 'listing')} at {plural(cv, 'venue')} with dates and links to book. Updated daily.", cpath, cbody, events_ld(cl[:60], places, today)))
            urls.append((cpath, "daily"))


    # ---- seasonal pages (pantomime, Christmas)
    season_hub = []
    for key, sd in seasonal.items():
        cfg, lst = sd["cfg"], sd["shows"]
        if len(lst) < 5:
            continue
        label, many, other = cfg["label"], cfg["many"], seasonal[cfg["other"]]
        yr = f"{sy}"
        vcount = len({s["theatre"] for s in lst})
        path = f"/{key}/"
        city_list = sorted(c for c, v in sd["by_city"].items() if v)
        jump = chips((f"#{slug(c)}", c, len(sd["by_city"][c])) for c in city_list)
        sections = ""
        for c in city_list:
            more = f' <a href="/{key}/{slug(c)}/" style="font-size:14px;font-family:var(--font-body);letter-spacing:0">All in {esc(c)}</a>' if c in sd["cities"] else ""
            sections += f'<h2 id="{slug(c)}">{esc(c)}{more}</h2>' + "".join(show_card(s, today, True, c) for s in sd["by_city"][c])
        nocity = [s for s in lst if not (places.get(s["theatre"]) or [None])[0]]
        if nocity:
            sections += "<h2>Other venues</h2>" + "".join(show_card(s, today, True, None) for s in nocity)
        faq = "".join(f"<h3>{esc(q)}</h3><p>{esc(a)}</p>" for q, a in cfg["faq"])
        if key == "pantomime":
            intro = "Pantomime is Britain's great festive tradition: fairytale stories, a booming dame, topical jokes and plenty of audience taking part. Whether you want a family outing or a night out with friends, find a pantomime near you below."
        else:
            intro = "From carol concerts and festive musicals to Christmas comedy, ballet and family shows, find something to enjoy this Christmas at venues across the UK."
        other_link = f'<a href="/{cfg["other"]}/">{esc(other["cfg"]["label"])}</a>'
        body = f"""<p class="crumbs"><a href="/">Home</a></p>
<h1>{esc(label)} {yr} across the UK</h1>
<p class="lede">{plural(len(lst), cfg['one'])} at {plural(vcount, 'venue')}. Dates come from each venue's own website and are refreshed daily.</p>
<p class="intro">{esc(intro)}</p>
<h2>Jump to your city</h2>
{jump}
{sections}
<h2>Questions</h2>
<div class="faq">{faq}</div>
<div class="cta"><p>Also see {other_link}, or search every show and venue.</p><a class="btn" href="/">Search all shows</a></div>"""
        ld = events_ld(lst, places, today)
        ld["@graph"].append({"@type": "FAQPage", "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in cfg["faq"]]})
        title = f"{label} {yr}: {len(lst)} shows across the UK, dates and tickets | Find a Show"
        desc = f"{plural(len(lst), cfg['one'])} at {plural(vcount, 'venue')} across the UK. Find {many} near you with dates and links to book."
        write(path, page(title, desc, path, body, ld))
        urls.append((path, "daily"))
        season_hub.append((path, f"{label} {yr}", len(lst)))
        for c in sorted(sd["cities"]):
            cl = sd["by_city"][c]
            cpath = f"/{key}/{slug(c)}/"
            cv = len({s["theatre"] for s in cl})
            cbody = f"""<p class="crumbs"><a href="/">Home</a> / <a href="/{key}/">{esc(label)}</a> / {esc(c)}</p>
<h1>{esc(label)} in {esc(c)} {yr}</h1>
<p class="lede">{plural(len(cl), cfg['one'])} at {plural(cv, 'venue')} in {esc(c)}. Dates come from each venue's own website and are refreshed daily.</p>
{"".join(show_card(s, today, True, c) for s in cl)}
<div class="cta"><p>See {esc(label.lower())} <a href="/{key}/">across the UK</a>, everything on in <a href="/cities/{slug(c)}/">{esc(c)}</a>, or search every show.</p><a class="btn" href="/">Search all shows</a></div>"""
            cld = events_ld(cl, places, today)
            write(cpath, page(f"{label} in {c} {yr}: dates and tickets | Find a Show", f"{plural(len(cl), cfg['one'])} in {c}. See dates and book tickets.", cpath, cbody, cld))
            urls.append((cpath, "daily"))


    # ---- newly added shows and venues
    cutoff = date.fromordinal(today.toordinal() - 7).isoformat()
    nv = {v: dd for v, dd in (data.get("new_venues") or {}).items() if dd >= cutoff and v in by_venue}
    fresh_shows = sorted((s for s in shows if s.get("added", "") >= cutoff and s["theatre"] not in nv), key=lambda s: (s["added"], s["title"].lower()), reverse=True)
    parts = ""
    if nv:
        parts += "<h2>New venues</h2>" + chips((f"/venues/{vslug[v]}/", v, len(by_venue[v])) for v in sorted(nv, key=lambda k: nv[k], reverse=True))
    if fresh_shows:
        cur, sec = None, ""
        for s in fresh_shows[:200]:
            if s["added"] != cur:
                cur = s["added"]
                dd = d(cur)
                sec += f"<h2>Added {dd.day} {dd.strftime('%b')}</h2>"
            sec += show_card(s, today, True, (places.get(s["theatre"]) or [None])[0])
        parts += sec
    if not parts:
        parts = '<p class="intro">Nothing new in the last 7 days yet. New shows and venues will appear here as they are announced.</p>'
    body = f"""<p class="crumbs"><a href="/">Home</a></p>
<h1>Newly added shows</h1>
<p class="lede">Shows and venues added to Find a Show in the last 7 days, newest first.</p>
{parts}
<div class="cta"><p>Looking for something specific? Search every show and venue.</p><a class="btn" href="/">Search all shows</a></div>"""
    write("/new/", page("Newly added shows | Find a Show", "The latest shows and venues added to Find a Show, newest first.", "/new/", body,
                        events_ld(fresh_shows[:60], places, today) if fresh_shows else None, noindex=not (fresh_shows or nv)))
    if fresh_shows or nv:
        urls.append(("/new/", "daily"))

    # ---- West End page
    we = [s for s in shows if s["theatre"] in WEST_END]
    if len(we) >= 5:
        wv = sorted({s["theatre"] for s in we})
        wbody = f"""<p class="crumbs"><a href="/">Home</a> / <a href="/cities/london/">London</a></p>
<h1>West End shows</h1>
<p class="lede">{plural(len(we), 'listing')} at {plural(len(wv), 'West End theatre')}, in date order. Dates come from each venue's own website and are refreshed daily.</p>
<h2>West End theatres</h2>
{chips((f"/venues/{vslug[v]}/", v, len([s for s in we if s['theatre'] == v])) for v in wv if v in vslug)}
<h2>What's on</h2>
{"".join(show_card(s, today, True, "London") for s in we[:150])}
<div class="cta"><p>See everything on in <a href="/cities/london/">London</a>, including concerts and comedy, or search every show.</p><a class="btn" href="/">Search all shows</a></div>"""
        write("/west-end-shows/", page("West End shows: theatre, musicals and tickets in London | Find a Show", f"{plural(len(we), 'West End listing')} across {plural(len(wv), 'theatre')}. See dates and book tickets for London theatre shows.", "/west-end-shows/", wbody, events_ld(we[:60], places, today)))
        urls.append(("/west-end-shows/", "daily"))

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
        '<p class="crumbs"><a href="/">Home</a></p><h1>Browse shows by type</h1><p class="lede">Pick a type of show.</p>' + chips(season_hub + cats + ([("/west-end-shows/", "West End shows", len(we))] if len(we) >= 5 else []))))
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
