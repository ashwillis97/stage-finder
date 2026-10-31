"""Add a Ticketmaster link ("tm") to shows that Ticketmaster sells, using their free Discovery API.

Runs after collect.py. Needs the TICKETMASTER_API_KEY secret; without it this does nothing.
Each venue is looked up once (cached in tm_venues.json), then its events are matched to our
listings by date and title. Nothing here can break the update: any failure just leaves "tm" off.
"""
import datetime as dt, json, os, pathlib, re, sys, time, urllib.parse, urllib.request
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
    with urllib.request.urlopen(f"{API}{path}?{q}", timeout=30) as r:
        data = json.loads(r.read())
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
                out.append({"name": e["name"], "date": d, "url": plain_url(e["url"]), "genre": from_ticketmaster((e.get("classifications") or [{}])[0])})
        if page + 1 >= ((data.get("page") or {}).get("totalPages") or 1):
            break
    return out


def match_show(show, events):
    """Earliest Ticketmaster performance inside the show's dates with a matching title."""
    hits = [e for e in events if show["start"] <= e["date"] <= show["end"] and title_match(show["title"], e["name"])]
    return min(hits, key=lambda e: e["date"]) if hits else None


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
    for r in data["shows"]:
        r.pop("tm", None)
    today = dt.date.today()
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
                    r["tm"] = hit["url"]
                    matched += 1
                    # Ticketmaster knows what type of show it is: use that unless the venue gave its own label
                    if hit.get("genre") and (not r.get("genre") or r.get("gsrc")):
                        r["genre"], r["gsrc"] = hit["genre"], "tm"
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
