"""Print ticket-link clicks per venue from the Cloudflare Analytics Engine dataset."""
import os, sys, requests

acct, tok = os.environ["CLOUDFLARE_ACCOUNT_ID"], os.environ["CLOUDFLARE_API_TOKEN"]
URL = f"https://api.cloudflare.com/client/v4/accounts/{acct}/analytics_engine/sql"

def q(sql):
    r = requests.post(URL, data=sql, headers={"Authorization": f"Bearer {tok}"}, timeout=60)
    if r.status_code != 200:
        print("Query failed:", r.status_code, r.text[:300]); sys.exit(1)
    return r.json().get("data", [])

for days in (7, 28):
    rows = q(f"SELECT index1 AS venue, SUM(_sample_interval) AS clicks FROM findashow_clicks WHERE timestamp > NOW() - INTERVAL '{days}' DAY GROUP BY venue ORDER BY clicks DESC LIMIT 40")
    tot = sum(int(float(r["clicks"])) for r in rows)
    print(f"\n=== TOP VENUES, last {days} days (ticket-link clicks; top 40 total {tot}) ===")
    for r in rows: print(f"{int(float(r['clicks'])):>6}  {r['venue']}")
rows = q("SELECT blob1 AS show, index1 AS venue, SUM(_sample_interval) AS clicks FROM findashow_clicks WHERE timestamp > NOW() - INTERVAL '28' DAY GROUP BY show, venue ORDER BY clicks DESC LIMIT 30")
print("\n=== TOP SHOWS, last 28 days ===")
for r in rows: print(f"{int(float(r['clicks'])):>6}  {r['show']}  ({r['venue']})")
rows = q("SELECT blob2 AS kind, SUM(_sample_interval) AS clicks FROM findashow_clicks WHERE timestamp > NOW() - INTERVAL '28' DAY GROUP BY kind")
print("\n=== BY LINK TYPE (tm = Ticketmaster affiliate, venue = venue's own link) ===")
for r in rows: print(f"{int(float(r['clicks'])):>6}  {r['kind']}")
