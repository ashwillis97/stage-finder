"""Weekly owner summary email: site health, visitors, Google Search Console, ticket clicks.

Sent through MailerLite to a private "Owner report" group (one subscriber: OWNER_EMAIL).
Every section fails soft; a missing piece shows as "unavailable" rather than stopping the email.
"""
import datetime as dt, html, json, os, pathlib, urllib.request, urllib.error, collections

ROOT = pathlib.Path(__file__).resolve().parent.parent
E = html.escape
ML = "https://connect.mailerlite.com/api"
ML_KEY = os.environ.get("MAILERLITE_API_KEY", "").strip()
FROM = os.environ.get("MAILERLITE_FROM", "").strip()
OWNER = os.environ.get("OWNER_EMAIL", "").strip()
CF_ACCT, CF_TOK = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip(), os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
SITE_TAG = "8386717571e94d43ae043733aa4dc407"


def http(method, url, body=None, headers=None, raw=False):
    data = body if raw else (json.dumps(body).encode() if body is not None else None)
    h = {"Accept": "application/json", "User-Agent": "FindAShow/1.0"}
    h.update(headers or {})
    if body is not None and not raw:
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:300]
    except Exception as e:
        return 0, repr(e)


def ml(method, path, body=None):
    st, txt = http(method, ML + path, body, {"Authorization": f"Bearer {ML_KEY}"})
    try:
        return st, json.loads(txt)
    except ValueError:
        return st, {"error": txt}


def site_stats():
    d = json.loads((ROOT / "shows.json").read_text(encoding="utf-8"))
    h = json.loads((ROOT / "health.json").read_text(encoding="utf-8")) if (ROOT / "health.json").exists() else {}
    today = dt.date.today().isoformat()
    week = (dt.date.today() - dt.timedelta(days=7)).isoformat()
    live = [r for r in d["shows"] if r["end"] >= today]
    src = collections.Counter("Skiddle" if r.get("src") == "skiddle" else "Ticketmaster link" if r.get("tm") else "Venue only" for r in live)
    return {
        "Listings": f"{len(live):,}", "Venues": f"{len({r['theatre'] for r in live}):,}",
        "Added in the last 7 days": f"{sum(1 for r in live if r.get('added', '') >= week):,}",
        "From Skiddle": f"{src['Skiddle']:,}", "With a Ticketmaster link": f"{src['Ticketmaster link']:,}",
    }, h


def visitors():
    if not (CF_ACCT and CF_TOK):
        return None
    end = dt.datetime.utcnow()
    out = {}
    for label, days in (("Last 7 days", 7), ("Last 28 days", 28)):
        q = ('{ viewer { accounts(filter:{accountTag:"%s"}) { t: rumPageloadEventsAdaptiveGroups(limit:1, filter:{siteTag:"%s", datetime_geq:"%s", datetime_leq:"%s"}) { count sum { visits } } } } }'
             % (CF_ACCT, SITE_TAG, (end - dt.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ"), end.strftime("%Y-%m-%dT%H:%M:%SZ")))
        st, txt = http("POST", "https://api.cloudflare.com/client/v4/graphql", {"query": q}, {"Authorization": f"Bearer {CF_TOK}"})
        try:
            g = json.loads(txt)["data"]["viewer"]["accounts"][0]["t"][0]
            out[label] = (g["sum"]["visits"], g["count"])
        except Exception:
            print("visitors:", st, txt[:200])
            return None
    return out


def clicks():
    if not (CF_ACCT and CF_TOK):
        return None
    url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCT}/analytics_engine/sql"
    res = {}
    for key, sql in (
        ("venues", "SELECT index1 AS k, SUM(_sample_interval) AS c FROM findashow_clicks WHERE timestamp > NOW() - INTERVAL '7' DAY GROUP BY k ORDER BY c DESC LIMIT 10"),
        ("shows", "SELECT blob1 AS k, SUM(_sample_interval) AS c FROM findashow_clicks WHERE timestamp > NOW() - INTERVAL '7' DAY GROUP BY k ORDER BY c DESC LIMIT 10"),
        ("kinds", "SELECT blob2 AS k, SUM(_sample_interval) AS c FROM findashow_clicks WHERE timestamp > NOW() - INTERVAL '7' DAY GROUP BY k"),
    ):
        st, txt = http("POST", url, sql, {"Authorization": f"Bearer {CF_TOK}"}, raw=True)
        try:
            res[key] = [(r["k"], int(float(r["c"]))) for r in json.loads(txt)["data"]]
        except Exception:
            print("clicks:", st, txt[:200])
            return None
    return res


def gsc():
    p = ROOT / "gsc_report.json"
    if not p.exists():
        return None
    try:
        g = json.loads(p.read_text(encoding="utf-8"))
        return g if isinstance(g.get("totals"), dict) else None
    except ValueError:
        return None


def table(rows, head=None):
    if not rows:
        return '<p style="color:#6a5f54;margin:4px 0">Nothing yet.</p>'
    t = '<table cellpadding="0" cellspacing="0" style="font-size:14px;width:100%">'
    for r in rows:
        t += "<tr>" + "".join(f'<td style="padding:3px 8px 3px 0;color:#1f1a16;{"text-align:right;font-weight:bold;white-space:nowrap" if i == 0 else ""}">{E(str(c))}</td>' for i, c in enumerate(r)) + "</tr>"
    return t + "</table>"


def section(title, inner):
    return f'<tr><td style="padding:18px 28px 0;font-family:Arial,sans-serif"><div style="font-size:16px;font-weight:bold;color:#a8391a;margin-bottom:6px">{E(title)}</div>{inner}</td></tr>'


def build():
    stats, health = site_stats()
    parts = [section("The site", table([(v, k) for k, v in stats.items()]))]
    broken = health.get("broken") or []
    parts.append(section("Venues needing attention", table([("", b) for b in broken]) if broken else '<p style="margin:4px 0;color:#1f1a16">All venue readers are working.</p>'))
    v = visitors()
    parts.append(section("Visitors (Cloudflare)", table([(f"{a:,} visits", f"{lbl} ({b:,} page views)") for lbl, (a, b) in v.items()]) if v else '<p style="margin:4px 0;color:#6a5f54">Unavailable. The Cloudflare token probably needs "Account Analytics: Read" permission.</p>'))
    g = gsc()
    if g:
        t = g["totals"]
        inner = table([(f'{int(t.get("clicks", 0)):,} clicks', "Google, last 28 days"), (f'{int(t.get("impressions", 0)):,} impressions', f'average position {t.get("position", 0):.1f}')])
        inner += '<div style="font-size:13px;font-weight:bold;margin-top:10px;color:#1f1a16">Top searches</div>' + table([(f'{r["clicks"]}', f'{r["key"]} ({r["impressions"]} impr)') for r in (g.get("queries") or [])[:8]])
        parts.append(section("Google Search Console", inner))
    else:
        parts.append(section("Google Search Console", '<p style="margin:4px 0;color:#6a5f54">Unavailable this week.</p>'))
    c = clicks()
    if c:
        parts.append(section("Ticket clicks, last 7 days", table([(n, k or "?") for k, n in c["venues"]]) + '<div style="font-size:13px;font-weight:bold;margin-top:10px">Top shows</div>' + table([(n, k) for k, n in c["shows"][:8]]) + '<div style="font-size:13px;font-weight:bold;margin-top:10px">By link type (tm = Ticketmaster, venue = own link)</div>' + table([(n, k) for k, n in c["kinds"]])))
    else:
        parts.append(section("Ticket clicks", '<p style="margin:4px 0;color:#6a5f54">Unavailable this week.</p>'))
    body = f"""<!doctype html><html><body style="margin:0;background:#faf6ef"><table width="100%" cellpadding="0" cellspacing="0" style="background:#faf6ef"><tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%">
<tr><td style="background:#160a12;padding:22px 28px;font-family:Arial,sans-serif;font-size:22px;font-weight:bold;color:#ffffff">Find a <span style="color:#ff8a5c">Show</span> &middot; weekly report</td></tr>
{''.join(parts)}
<tr><td style="padding:24px 28px 32px;font-family:Arial,sans-serif;font-size:12px;color:#6a5f54">Sent automatically every Monday. <a href="{{$unsubscribe}}" style="color:#6a5f54">Unsubscribe</a></td></tr>
</table></td></tr></table></body></html>"""
    return body


def main():
    body = build()
    (ROOT / "owner_report_preview.html").write_text(body.replace("{$unsubscribe}", "#"), encoding="utf-8")
    if not (ML_KEY and FROM and OWNER):
        print("Missing MAILERLITE_API_KEY, MAILERLITE_FROM or OWNER_EMAIL; preview only")
        return
    st, groups = ml("GET", "/groups?limit=100")
    g = next((x for x in groups.get("data", []) if x["name"] == "Owner report"), None) if st == 200 else None
    if not g:
        st, made = ml("POST", "/groups", {"name": "Owner report"})
        print("create group:", st)
        g = made.get("data")
    if not g:
        print("No group, not sending")
        return
    st, sub = ml("POST", "/subscribers", {"email": OWNER, "groups": [g["id"]]})
    print("subscriber:", st, (sub.get("data") or {}).get("status"), sub.get("message", ""))
    day = dt.date.today().isoformat()
    st, camp = ml("POST", "/campaigns", {"name": f"Owner report {day}", "type": "regular", "groups": [g["id"]],
                                          "emails": [{"subject": f"Find a Show weekly report, {day}", "from_name": "Find a Show", "from": FROM, "content": body}]})
    print("create campaign:", st, camp.get("message", ""), camp.get("errors", ""))
    if st in (200, 201):
        st, res = ml("POST", f"/campaigns/{camp['data']['id']}/schedule", {"delivery": "instant"})
        print("send:", st, res.get("message", ""))


if __name__ == "__main__":
    main()
