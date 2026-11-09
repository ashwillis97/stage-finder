"""Add a Ticketmaster link ("tm") to shows that Ticketmaster sells, using their free Discovery API.

Runs after collect.py. Needs the TICKETMASTER_API_KEY secret; without it this does nothing.
Each venue is looked up once (cached in tm_venues.json), then its events are matched to our
listings by date and title. Nothing here can break the update: any failure just leaves "tm" off.
"""
import datetime as dt, json, os, pathlib, re, sys, time, urllib.error, urllib.parse, urllib.request
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from genre import from_ticketmaster

ROOT = pathlib.Path(__file__).resolve().parent.parent
API = "https://app.ticketmaster.com/discovery/v2/"
STOP = {"the", "a", "an", "and", "of", "in", "at", "live", "tour", "presents", "with", "show", "tickets", "ticket"}


def norm(s):
    s = re.sub(r"[^a-z0-9 ]+", " ", s.lower().replace("&", " and "))
    return " ".join(w for w in s.split() if w not in STOP)


def tokens(s):
    return set(norm(s).split())


def title_match(ours, theirs):
    a, b = norm(ours), norm(theirs)
    if not a or not b:
        return False
    if a == b:
        return True
    if len(a) >= 6 and len(b) >= 6 and (a in b or b in a):
        return True
    ta, tb = tokens(ours), tokens(theirs)
    return bool(ta and tb) and len(ta & tb) / len(ta | tb) >= 0.6


def venue_score(ours, theirs):
    ta, tb = tokens(ours), tokens(theirs)
    return len(ta & tb) / len(ta | tb) if ta and tb else 0


def plain_url(u):
    """The API may hand back a ready-made affiliate link; keep only the Ticketmaster page inside it."""
    try:
        p = urllib.parse.urlparse(u)
        if p.hostname and p.hostname.endswith("evyy.net"):
            inner = urllib.parse.parse_qs(p.query).get("u")
            if inner:
                return inner[0]
    except ValueError:
        pass
    return u


def call(path, params, key):
    q = urllib.parse.urlencode(dict(params, apikey=key))
    for attempt in range(3):
        try:
            with urllib.request.urlopen(f"{API}{path}?{q}", timeout=30) as r:
                data = json.loads(r.read())
            break
        except urllib.error.HTTPError as e:
            if e.code != 429 or attempt == 2:
                raise
            time.sleep(3 * (attempt + 1))
    time.sleep(0.25)  # stay well inside the rate limit
    return data


def find_venue(name, city, key):
    data = call("venues.json", {"keyword": name, "countryCode": "GB", "size": 20}, key)
    best, best_s = None, 0.0
    for v in (data.get("_embedded") or {}).get("venues", []):
        s = venue_score(name, v.get("name", ""))
        vc = ((v.get("city") or {}).get("name") or "").lower()
        if city and vc and city.lower() not in vc and vc not in city.lower():
            s -= 0.3
        if s > best_s:
            best, best_s = v, s
    return best["id"] if best and best_s >= 0.5 else None


def venue_events(vid, key):
    out = []
    for page in range(2):
        data = call("events.json", {"venueId": vid, "countryCode": "GB", "size": 200, "page": page, "sort": "date,asc"}, key)
        for e in (data.get("_embedded") or {}).get("events", []):
            d = ((e.get("dates") or {}).get("start") or {}).get("localDate")
            if d and e.get("url") and e.get("name"):
                cls = (e.get("classifications") or [{}])[0]
                seg = (((cls or {}).get("segment") or {}).get("name") or "").lower()
                code = (((e.get("dates") or {}).get("status") or {}).get("code") or "").lower()
                sale0 = (((e.get("sales") or {}).get("public") or {}).get("startDateTime") or "")
                started = bool(sale0) and sale0 <= dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                far = d >= (dt.date.today() + dt.timedelta(days=2)).isoformat()
                out.append({"name": e["name"], "date": d, "url": plain_url(e["url"]), "genre": from_ticketmaster(cls), "seg": seg,
                            "sold": code == "offsale" and started and far, "cancelled": code in ("cancelled", "canceled")})
        if page + 1 >= ((data.get("page") or {}).get("totalPages") or 1):
            break
    return out


def flag(r, evs):
    """Mark a listing sold out or cancelled only when every Ticketmaster performance of it is."""
    r.pop("soldout", None)
    r.pop("cancelled", None)
    if evs and all(e.get("cancelled") for e in evs):
        r["cancelled"] = True
    elif evs and all(e.get("sold") or e.get("cancelled") for e in evs):
        r["soldout"] = True


def match_show(show, events):
    """Earliest Ticketmaster performance inside the show's dates with a matching title."""
    hits = [e for e in events if show["start"] <= e["date"] <= show["end"] and title_match(show["title"], e["name"])]
    return min(hits, key=lambda e: e["date"]) if hits else None


TM_NOISE = re.compile(r"parking|\bvip\b|hospitality|package|upgrade|meet (&|and) greet|fast.?track|lounge|premium seat|gift|voucher|camping|coach|shuttle|\btour\b.*\b(guided|backstage)\b", re.I)


def rows_from_events(theatre, events):
    """Venues we can't read ourselves: build one listing per title from its Ticketmaster dates."""
    groups = {}
    for e in events:
        if e.get("seg") == "sports" or TM_NOISE.search(e["name"]):
            continue
        key = re.sub(r"\s+", " ", e["name"]).strip().lower()
        g = groups.setdefault(key, {"title": re.sub(r"\s+", " ", e["name"]).strip(), "dates": [], "hit": e, "evs": []})
        g["evs"].append(e)
        g["dates"].append(e["date"])
        if e["date"] < g["hit"]["date"]:
            g["hit"] = e
    out = []
    for g in groups.values():
        hit = g["hit"]
        r = {"title": g["title"], "theatre": theatre, "genre": hit.get("genre") or "", "start": min(g["dates"]), "end": max(g["dates"]), "url": hit["url"], "tm": hit["url"]}
        if r["genre"]:
            r["gsrc"] = "tm"
        flag(r, g["evs"])
        out.append(r)
    return out


def main():
    key = os.environ.get("TICKETMASTER_API_KEY", "").strip()
    if not key:
        print("No TICKETMASTER_API_KEY, skipping Ticketmaster matching")
        return
    shows_path, cache_path = ROOT / "shows.json", ROOT / "tm_venues.json"
    data = json.loads(shows_path.read_text(encoding="utf-8"))
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    cities = {}
    for f in ("venues.json", "venues_new.json"):
        if (ROOT / f).exists():
            for v in json.loads((ROOT / f).read_text(encoding="utf-8"))["venues"]:
                cities[v["name"]] = v.get("city", "")
    prev = {(r["theatre"], r["title"], r["start"]): {k: r[k] for k in ("tm", "soldout", "cancelled") if k in r} for r in data["shows"]}
    for r in data["shows"]:
        r.pop("tm", None)
        r.pop("soldout", None)
        r.pop("cancelled", None)
    today = dt.date.today()
    tm_fed = []
    if (ROOT / "venues.json").exists():
        tm_fed = [v for v in json.loads((ROOT / "venues.json").read_text(encoding="utf-8"))["venues"] if v.get("reader") == "tm" or v.get("tm_fill")]
    cov = data.setdefault("coverage", {"none": [], "partial": {}}).setdefault("partial", {})
    AUTO = "Not updated automatically yet, so these listings may be out of date."
    FILL = "Shows here come from Ticketmaster, so ones sold only through the venue may be missing."
    for v in tm_fed:
        name = v["name"]
        try:
            if v.get("tm_ids"):
                ids = v["tm_ids"]
            else:
                entry = cache.get(name)
                if entry is None or (entry["id"] is None and (today - dt.date.fromisoformat(entry["checked"])).days >= 14):
                    entry = cache[name] = {"id": find_venue(name, v.get("city", ""), key), "checked": today.isoformat()}
                if not entry["id"]:
                    continue
                ids = [entry["id"]]
            evs = [e for i in ids for e in venue_events(i, key)]
            fresh = [r for r in rows_from_events(name, evs) if r["end"] >= today.isoformat()]
        except Exception as e:
            print(f"{name}: Ticketmaster listing failed: {e!r}"[:200])
            continue
        if fresh and v.get("reader") == "tm":  # only replace the old listings when we actually got new ones
            data["shows"] = [r for r in data["shows"] if r["theatre"] != name] + fresh
            cov.pop(name, None)
            print(f"{name}: {len(fresh)} shows from Ticketmaster")
        elif fresh:  # venue has its own reader; Ticketmaster fills the gaps or replaces a reader that is failing
            if cov.get(name) == AUTO:  # own reader is failing: Ticketmaster is the source
                data["shows"] = [r for r in data["shows"] if r["theatre"] != name] + fresh
                cov[name] = FILL
                print(f"{name}: {len(fresh)} shows from Ticketmaster (own reader failing)")
            else:  # own reader works but is incomplete: add Ticketmaster shows we don't already have
                def key_of(r):
                    return (r["start"], "".join(re.findall(r"[a-z0-9]+", r["title"].lower()))[:10])
                have = {key_of(r) for r in data["shows"] if r["theatre"] == name}
                add = [r for r in fresh if key_of(r) not in have]
                data["shows"] += add
                print(f"{name}: {len(add)} extra shows from Ticketmaster")
    data["shows"].sort(key=lambda r: (r["start"], r["title"]))
    matched, venues_used, errors = 0, 0, 0
    for theatre in sorted({r["theatre"] for r in data["shows"]}):
        entry = cache.get(theatre)
        try:
            if entry is None or (entry["id"] is None and (today - dt.date.fromisoformat(entry["checked"])).days >= 14):
                entry = cache[theatre] = {"id": find_venue(theatre, cities.get(theatre, ""), key), "checked": today.isoformat()}
            if not entry["id"]:
                continue
            events = venue_events(entry["id"], key)
        except Exception as e:  # one venue failing must not stop the rest
            errors += 1
            print(f"{theatre}: Ticketmaster lookup failed: {e!r}"[:200])
            if errors >= 10:
                print("Too many Ticketmaster errors, stopping")
                break
            continue
        venues_used += 1
        for r in data["shows"]:
            if r["theatre"] == theatre:
                hit = match_show(r, events)
                if hit:
                    flag(r, [e for e in events if r["start"] <= e["date"] <= r["end"] and title_match(r["title"], e["name"])])
                    r["tm"] = hit["url"]
                    matched += 1
                    # Ticketmaster knows what type of show it is: use that unless the venue gave its own label
                    if hit.get("genre") and (not r.get("genre") or r.get("gsrc")):
                        r["genre"], r["gsrc"] = hit["genre"], "tm"
    if errors >= 10:  # the run was cut short (e.g. rate limit): keep last run's links rather than losing them all
        kept = 0
        for r in data["shows"]:
            old = prev.get((r["theatre"], r["title"], r["start"]))
            if old and "tm" not in r:
                r.update(old)
                kept += 1
        print(f"Run cut short: kept {kept} Ticketmaster links from the previous run")
    so = [r for r in data["shows"] if r.get("soldout")]
    ca = [r for r in data["shows"] if r.get("cancelled")]
    print(f"Sold out: {len(so)}, cancelled: {len(ca)}; samples: " + "; ".join(f"{r['title']} ({r['theatre']}, {r['start']})" for r in so[:12]))
    cache_path.write_text(json.dumps(cache, indent=1, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    shows_path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    hp = ROOT / "health.json"
    if hp.exists():
        h = json.loads(hp.read_text(encoding="utf-8"))
        h["ticketmaster"] = {"venues_found": sum(1 for v in cache.values() if v["id"]), "shows_matched": matched, "errors": errors}
        hp.write_text(json.dumps(h, indent=1, ensure_ascii=False), encoding="utf-8")
    summ = os.environ.get("GITHUB_STEP_SUMMARY")
    if summ:
        with open(summ, "a", encoding="utf-8") as fh:
            fh.write(f"\n### Ticketmaster\n{matched} shows matched across {venues_used} venues ({errors} errors).\n")
    print(f"Ticketmaster: {matched} shows matched across {venues_used} venues, {errors} errors")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("Ticketmaster step failed (listings are unaffected):", repr(e))
