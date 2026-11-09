"""Add gigs, comedy, festivals, theatre and kids' events from Skiddle (free affiliate API).

Runs after ticketmaster.py. Needs the SKIDDLE_API_KEY secret; without it this does nothing.
Skiddle rows carry src="skiddle" and are rebuilt from scratch every run. Venues we already read
ourselves are skipped, and any failure leaves the existing listings untouched.
"""
import datetime as dt, json, os, pathlib, re, sys, time, urllib.parse, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
API = "https://www.skiddle.com/api/v1/events/search/"
CODES = {"LIVE": "Music", "COMEDY": "Comedy", "THEATRE": "Play", "KIDS": "Family", "FEST": "Festival"}
PAGES = 10          # 100 events per page per category
MIN_EVENTS = 2      # venues with fewer upcoming events get no page of their own
MAX_VENUES = 400
NOISE = re.compile(r"\b(open mic|quiz|karaoke|brunch|bingo|dj set|club night|rave|vip upgrade|parking|camping|travel|coach|shuttle|locker)\b", re.I)


def norm(s):
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower().replace("&", " and ")).strip()


def get(params, key):
    q = urllib.parse.urlencode(dict(params, api_key=key))
    req = urllib.request.Request(f"{API}?{q}", headers={"User-Agent": "FindAShow/1.0 (+https://findashow.co.uk)"})
    with urllib.request.urlopen(req, timeout=40) as r:
        data = json.loads(r.read())
    time.sleep(0.4)
    return data


def fetch(key, today):
    out = []
    for code in CODES:
        for page in range(PAGES):
            try:
                d = get({"latitude": 54.0, "longitude": -2.5, "radius": 450, "eventcode": code, "limit": 100,
                         "offset": page * 100, "order": "date", "minDate": today.isoformat(), "description": 0}, key)
            except Exception as e:
                print(f"Skiddle {code} page {page}: {e!r}")
                break
            res = d.get("results") or []
            for e in res:
                e["_code"] = code
            out += res
            if len(res) < 100:
                break
    return out


def regions(postcodes):
    """postcode -> site region, via postcodes.io (bulk)."""
    out = {}
    pcs = sorted(p for p in postcodes if p)
    for i in range(0, len(pcs), 100):
        try:
            req = urllib.request.Request("https://api.postcodes.io/postcodes", data=json.dumps({"postcodes": pcs[i:i + 100]}).encode(),
                                         headers={"Content-Type": "application/json"})
            res = json.loads(urllib.request.urlopen(req, timeout=30).read()).get("result") or []
        except Exception as e:
            print("postcodes.io:", repr(e))
            continue
        for r in res:
            h = r.get("result")
            if not h:
                continue
            country, reg = h.get("country") or "", h.get("region") or ""
            out[r["query"]] = (country if country in ("Scotland", "Wales") else "Northern Ireland" if country == "Northern Ireland" else
                               "London" if reg == "London" else "Midlands" if reg in ("East Midlands", "West Midlands") else
                               "North" if reg in ("North East", "North West", "Yorkshire and The Humber") else
                               "South & East" if reg else "")
    return out


def main():
    key = os.environ.get("SKIDDLE_API_KEY", "").strip()
    if not key:
        print("No SKIDDLE_API_KEY, skipping Skiddle")
        return
    path = ROOT / "shows.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    today = dt.date.today()
    events = fetch(key, today)
    print(f"Skiddle: {len(events)} events fetched")
    if not events:
        return  # keep whatever we had
    ours = {norm(r["theatre"]) for r in data["shows"] if r.get("src") != "skiddle"}
    have = {(r["start"], re.sub(r"[^a-z0-9]", "", r["title"].lower())[:10]) for r in data["shows"] if r.get("src") != "skiddle"}
    groups = {}
    for e in events:
        v = e.get("venue") or {}
        vname, title = (v.get("name") or "").strip(), re.sub(r"\s+", " ", e.get("eventname") or "").strip()
        date = (e.get("date") or e.get("startdate") or "")[:10]
        if not (vname and title and date and e.get("link")) or str(e.get("cancelled")) == "1" or NOISE.search(title):
            continue
        if norm(vname) in ours or (date, re.sub(r"[^a-z0-9]", "", title.lower())[:10]) in have:
            continue
        end = (e.get("enddate") or date)[:10]
        g = groups.setdefault((vname, title.lower()), {"venue": v, "title": title, "start": date, "end": max(date, end), "url": e["link"], "code": e["_code"]})
        g["start"], g["end"] = min(g["start"], date), max(g["end"], date, end)
    by_venue = {}
    for g in groups.values():
        by_venue.setdefault(g["venue"]["name"].strip(), []).append(g)
    keep = sorted((v for v, l in by_venue.items() if len(l) >= MIN_EVENTS), key=lambda v: -len(by_venue[v]))[:MAX_VENUES]
    rows, places = [], {}
    reg = regions({(by_venue[v][0]["venue"].get("postcode") or "").strip().upper() for v in keep})
    for v in keep:
        vi = by_venue[v][0]["venue"]
        try:
            lat, lng = round(float(vi.get("latitude")), 4), round(float(vi.get("longitude")), 4)
        except (TypeError, ValueError):
            continue
        town = (vi.get("town") or "").strip()
        if not town:
            continue
        places[v] = [town, lat, lng, reg.get((vi.get("postcode") or "").strip().upper(), "")]
        for g in by_venue[v]:
            rows.append({"title": g["title"], "theatre": v, "genre": CODES[g["code"]], "start": g["start"], "end": g["end"], "url": g["url"], "src": "skiddle"})
    if not rows:
        return
    data["shows"] = [r for r in data["shows"] if r.get("src") != "skiddle"] + rows
    data.setdefault("places", {}).update(places)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"Skiddle: added {len(rows)} listings at {len(places)} venues")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # never break the update
        print("Skiddle failed:", repr(e))
