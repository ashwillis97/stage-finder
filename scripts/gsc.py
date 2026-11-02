"""Pull the last 28 days from Google Search Console (read-only) into gsc_report.json."""
import datetime as dt, json, os, pathlib, sys
import google.auth.transport.requests as gr
from google.oauth2 import service_account

ROOT = pathlib.Path(__file__).resolve().parent.parent
raw = os.environ.get("GSC_SERVICE_ACCOUNT_JSON", "").strip()
if not raw:
    sys.exit("No GSC_SERVICE_ACCOUNT_JSON secret")
creds = service_account.Credentials.from_service_account_info(json.loads(raw), scopes=["https://www.googleapis.com/auth/webmasters.readonly"])
sess = gr.AuthorizedSession(creds)
BASE = "https://searchconsole.googleapis.com/webmasters/v3"

r = sess.get(BASE + "/sites")
print("sites:", r.status_code)
sites = [s["siteUrl"] for s in r.json().get("siteEntry", [])] if r.ok else []
print("visible properties:", sites, r.text[:200] if not r.ok else "")
site = next((s for s in sites if "findashow" in s), None)
out = {"properties": sites, "site": site}
if site:
    end = dt.date.today() - dt.timedelta(days=2)  # Search Console data lags about two days
    start = end - dt.timedelta(days=27)
    import urllib.parse
    q = lambda body: sess.post(f"{BASE}/sites/{urllib.parse.quote(site, safe='')}/searchAnalytics/query", json=dict(body, startDate=start.isoformat(), endDate=end.isoformat()))
    t = q({})
    out["totals"] = t.json().get("rows", [{}])[0] if t.ok else t.text[:200]
    for name, dim in (("queries", "query"), ("pages", "page"), ("days", "date")):
        x = q({"dimensions": [dim], "rowLimit": 25 if dim != "date" else 40})
        out[name] = [{"key": r["keys"][0], "clicks": r["clicks"], "impressions": r["impressions"], "ctr": round(r["ctr"], 3), "position": round(r["position"], 1)} for r in x.json().get("rows", [])] if x.ok else x.text[:200]
    sm = sess.get(f"{BASE}/sites/{urllib.parse.quote(site, safe='')}/sitemaps")
    out["sitemaps"] = [{"path": s["path"], "errors": s.get("errors"), "warnings": s.get("warnings"), "submitted": [c.get("submitted") for c in s.get("contents", [])]} for s in sm.json().get("sitemap", [])] if sm.ok else sm.text[:200]
    out["range"] = [start.isoformat(), end.isoformat()]
(ROOT / "gsc_report.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
print(json.dumps({k: v for k, v in out.items() if k not in ("queries", "pages", "days")}, indent=1)[:1500])
