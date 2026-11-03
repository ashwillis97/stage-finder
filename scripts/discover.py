"""Find UK venues on Ticketmaster with lots of music / arts events that we don't list yet."""
import datetime as dt, json, os, pathlib, sys, time, urllib.parse, urllib.request
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from ticketmaster import norm, venue_score

ROOT = pathlib.Path(__file__).resolve().parent.parent
KEY = os.environ.get("TICKETMASTER_API_KEY", "").strip()
API = "https://app.ticketmaster.com/discovery/v2/"
CITIES = """Aberdeen Aberystwyth Barnsley Basildon Bath Belfast Birmingham Blackburn Blackpool Bolton Bournemouth Bradford Brighton Bristol Burnley Bury Buxton Cambridge Canterbury Cardiff Carlisle Chelmsford Cheltenham Chester Chesterfield Colchester Coventry Crawley Darlington Derby Doncaster Dundee Durham Eastbourne Edinburgh Exeter Falkirk Glasgow Gloucester Guildford Halifax Harrogate Hastings Hereford Huddersfield Hull Inverness Ipswich Kendal Lancaster Leeds Leicester Lincoln Liverpool Llandudno Luton Maidstone Manchester Margate Middlesbrough Milton Keynes Newcastle Newport Northampton Norwich Nottingham Oxford Paisley Perth Peterborough Plymouth Poole Portsmouth Preston Reading Salford Salisbury Scarborough Sheffield Shrewsbury Southampton Southend Southport St Albans Stevenage Stockport Stoke Sunderland Swansea Swindon Taunton Torquay Truro Warrington Watford Wigan Winchester Windsor Wolverhampton Worcester Woking Wycombe Yeovil York Londonderry Newry Bangor Wrexham Barrow Basingstoke Bedford Bexhill Blackheath Bromley Croydon Kingston Richmond Wimbledon Hayes""".split()
# multi-word cities
CITIES = [c for c in CITIES if c not in ("Milton", "Keynes", "St", "Albans", "Stoke")] + ["Milton Keynes", "St Albans", "Stoke-on-Trent"]


EXTRA = """Accrington Aldershot Alloa Andover Ayr Banbury Barnstaple Basingstoke Bedford Berwick Beverley Bideford Bishop-Auckland Bognor Boston Bracknell Bridgwater Bridlington Burton Bury-St-Edmunds Camberley Cannock Chatham Chesham Chichester Chippenham Clacton Colwyn Crewe Cromer Cwmbran Dartford Daventry Dorchester Dudley Dumfries Dunfermline Eastleigh Ely Epsom Evesham Fareham Farnham Folkestone Gateshead Gillingham Gosport Grantham Grimsby Hartlepool Harlow Hemel Hertford Hinckley Horsham Hove Ilkley Keighley Kettering Kidderminster Kilmarnock Kirkcaldy Knutsford Lancing Leamington Leatherhead Lichfield Loughborough Lowestoft Macclesfield Maidenhead Malvern Mansfield Newbury Newquay Northwich Nuneaton Oldham Penzance Pontypridd Rochdale Rotherham Rugby Runcorn Salisbury Sevenoaks Skegness Slough Solihull Southwold Stafford Stirling Stratford Sudbury Sutton Tamworth Telford Tewkesbury Tunbridge Wakefield Walsall Warwick Wellingborough Weston Weymouth Whitby Whitehaven Widnes Worthing Wrexham Yarmouth""".split()
CITIES = CITIES + [c.replace("-", " ") for c in EXTRA]


def call(path, params):
    q = urllib.parse.urlencode(dict(params, apikey=KEY))
    for attempt in range(3):
        try:
            with urllib.request.urlopen(f"{API}{path}?{q}", timeout=30) as r:
                d = json.loads(r.read())
            time.sleep(0.25)
            return d
        except Exception as e:
            time.sleep(2)
    return {}


def existing_names():
    out = []
    for f in ("venues.json", "venues_new.json"):
        p = ROOT / f
        if p.exists():
            out += [v["name"] for v in json.loads(p.read_text(encoding="utf-8"))["venues"]]
    return out


found = {}
end = (dt.date.today() + dt.timedelta(days=270)).isoformat() + "T00:00:00Z"
for city in CITIES:
    for page in range(3):
        d = call("events.json", {"countryCode": "GB", "city": city, "segmentId": "KZFzniwnSyZfZ7v7nJ,KZFzniwnSyZfZ7v7na", "size": 200, "page": page, "endDateTime": end})
        evs = (d.get("_embedded") or {}).get("events", [])
        for e in evs:
            for v in (e.get("_embedded") or {}).get("venues", []):
                x = found.setdefault(v["id"], {"id": v["id"], "name": v.get("name", ""), "city": (v.get("city") or {}).get("name", ""), "postcode": v.get("postalCode", ""), "events": set()})
                x["events"].add(e["id"])
        if page + 1 >= ((d.get("page") or {}).get("totalPages") or 1):
            break
have = existing_names()
rows = []
for v in found.values():
    n = len(v["events"])
    best = max((venue_score(v["name"], h) for h in have), default=0)
    rows.append({"id": v["id"], "name": v["name"], "city": v["city"], "postcode": v["postcode"], "events": n, "nearest_existing_score": round(best, 2)})
rows.sort(key=lambda r: -r["events"])
new = [r for r in rows if r["nearest_existing_score"] < 0.6 and r["events"] >= 3]
(ROOT / "discovered_venues.json").write_text(json.dumps(new, indent=1, ensure_ascii=False), encoding="utf-8")
import re
KW = re.compile(r"theatre|theater|hall|arena|centre|center|playhouse|opera|auditorium|assembly|corn exchange|pavilion|dome|palace|empire|forum|guildhall|civic|concert|arts|academy|lyceum|apollo|regent|royal|grand|rep\b|studio|amphitheatre|castle|park|cathedral|abbey|church|college|university", re.I)
BAD = re.compile(r"pub\b|bar\b|club\b|inn\b|tavern|union|social|arms|hotel|stadium|racecourse|golf|rugby|football|cricket|fc\b|school|ice|sports|snooker", re.I)
new = [r for r in new if KW.search(r["name"]) and not BAD.search(r["name"])]
print(f"{len(found)} venues seen, {len(new)} candidate theatres/halls not in our list")
for r in new[:200]:
    print(f"  {r['events']:3d}  {r['name']} | {r['city']} | {r['postcode']} | {r['id']}")
