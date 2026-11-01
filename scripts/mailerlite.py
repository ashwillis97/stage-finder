"""MailerLite helper: `check` tests the API key and makes sure a 'Weekly digest' group exists.

Writes mailerlite_info.json (group id and counts only, no addresses or keys).
"""
import json, os, pathlib, sys, urllib.request, urllib.error

ROOT = pathlib.Path(__file__).resolve().parent.parent
API = "https://connect.mailerlite.com/api"
KEY = os.environ.get("MAILERLITE_API_KEY", "").strip()


def call(method, path, body=None):
    req = urllib.request.Request(API + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": "Bearer " + KEY, "Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, {"error": e.read().decode("utf-8", "replace")[:300]}


def check():
    info = {"key_present": bool(KEY)}
    if not KEY:
        print("No MAILERLITE_API_KEY secret")
    else:
        st, groups = call("GET", "/groups?limit=100")
        info["groups_status"] = st
        if st == 200:
            by = {g["name"]: g for g in groups.get("data", [])}
            if "Weekly digest" not in by:
                st2, made = call("POST", "/groups", {"name": "Weekly digest"})
                info["group_create_status"] = st2
                if st2 in (200, 201):
                    by["Weekly digest"] = made["data"]
            g = by.get("Weekly digest")
            info["group_id"] = g["id"] if g else None
            info["subscribers_in_group"] = (g or {}).get("active_count")
        else:
            info["groups_error"] = groups.get("error")
        for status in ("active", "unconfirmed", "unsubscribed", "bounced", "junk"):
            st, subs = call("GET", f"/subscribers?limit=100&filter[status]={status}")
            info["subscribers_" + status] = len(subs.get("data", [])) if st == 200 else f"error {st}"
        st, subs = call("GET", "/subscribers?limit=1")
        info["subscribers_status"] = st
        info["subscribers_total"] = (subs.get("meta") or {}).get("total")
        st, forms = call("GET", "/forms/embedded?limit=25")
        info["forms_status"] = st
        info["forms"] = [{"id": f.get("id"), "name": f.get("name"), "opted_in": f.get("opted_in_count")} for f in forms.get("data", [])] if st == 200 else forms.get("error")
    (ROOT / "mailerlite_info.json").write_text(json.dumps(info, indent=1), encoding="utf-8")
    print(json.dumps(info, indent=1))


import datetime as dt, html, urllib.parse

AFF_BASE, AFF_PROP = "https://ticketmaster.evyy.net/c/8068961/264167/4272", "9082472"
SITE = "https://findashow.co.uk"
DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def link(s):
    if s.get("tm"):
        return AFF_BASE + "?u=" + urllib.parse.quote(s["tm"], safe="") + "&partnerpropertyid=" + AFF_PROP
    return s["url"]


def when(s):
    a, b = dt.date.fromisoformat(s["start"]), dt.date.fromisoformat(s["end"])
    f = lambda d: f"{DOW[d.weekday()]} {d.day} {MON[d.month - 1]}"
    return f(a) if a == b else f"{f(a)} to {f(b)}"


def pick_new(days=7, limit=12):
    data = json.loads((ROOT / "shows.json").read_text(encoding="utf-8"))
    today = dt.date.today()
    cutoff = (today - dt.timedelta(days=days)).isoformat()
    rows = [r for r in data["shows"] if r.get("added", "") >= cutoff and r["end"] >= today.isoformat() and r["start"] >= today.isoformat()]
    rows.sort(key=lambda r: (not r.get("tm"), r["start"], r["title"]))  # Ticketmaster-matched first, then soonest
    return len(rows), rows[:limit]


def build_html(total, rows):
    e = html.escape
    cards = "".join(
        f'<tr><td style="padding:0 0 12px"><table width="100%" cellpadding="0" cellspacing="0" style="background:#ffffff;border:1px solid #e6dfd3;border-radius:16px"><tr><td style="padding:16px 18px;font-family:Arial,sans-serif">'
        f'<div style="font-size:20px;font-weight:bold;color:#1f1a16;line-height:1.2">{e(r["title"])}</div>'
        f'<div style="font-size:14px;color:#6a5f54;margin-top:4px">{e(r["theatre"])} &middot; {e(when(r))}</div>'
        f'<div style="margin-top:12px"><a href="{e(link(r))}" style="display:inline-block;background:#c4411d;color:#ffffff;text-decoration:none;font-weight:bold;font-size:14px;padding:9px 16px;border-radius:10px">Tickets &amp; info</a></div>'
        f'</td></tr></table></td></tr>' for r in rows)
    return f"""<!doctype html><html><body style="margin:0;background:#faf6ef"><table width="100%" cellpadding="0" cellspacing="0" style="background:#faf6ef"><tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%">
<tr><td style="background:#160a12;padding:22px 28px;font-family:Arial,sans-serif;font-size:24px;font-weight:bold;color:#ffffff">Find a <span style="color:#ff8a5c">Show</span></td></tr>
<tr><td style="padding:28px 28px 8px;font-family:Arial,sans-serif"><div style="font-size:26px;font-weight:bold;color:#1f1a16;line-height:1.2">{total} new shows this week</div><div style="font-size:15px;color:#6a5f54;margin-top:8px">Added across the UK since last week, soonest first.</div></td></tr>
<tr><td style="padding:16px 28px 0"><table width="100%" cellpadding="0" cellspacing="0">{cards}</table></td></tr>
<tr><td style="padding:4px 28px 0;font-family:Arial,sans-serif"><a href="{SITE}/new/" style="font-size:15px;font-weight:bold;color:#a8391a">See everything new on Find a Show</a></td></tr>
<tr><td style="padding:24px 28px 32px;font-family:Arial,sans-serif;font-size:12px;line-height:1.5;color:#6a5f54">Some ticket links are affiliate links, so we may earn a commission at no extra cost to you. You're getting this because you signed up at findashow.co.uk. <a href="{{$unsubscribe}}" style="color:#6a5f54">Unsubscribe</a></td></tr>
</table></td></tr></table></body></html>"""


def digest(send):
    total, rows = pick_new()
    print(f"{total} new shows, {len(rows)} in the email")
    if not rows:
        print("Nothing new, no email")
        return
    body = build_html(total, rows)
    (ROOT / "digest_preview.html").write_text(body.replace("{$unsubscribe}", "#"), encoding="utf-8")
    if not send:
        return
    frm, name = os.environ.get("MAILERLITE_FROM", "").strip(), "Find a Show"
    st, groups = call("GET", "/groups?limit=100")
    g = next((x for x in groups.get("data", []) if x["name"] == "Weekly digest"), None) if st == 200 else None
    if not g or not frm:
        print("Missing group or MAILERLITE_FROM secret, not sending")
        return
    if not (g.get("active_count") or 0):
        print("No confirmed subscribers yet, not sending")
        return
    subject = f"{total} new shows on Find a Show this week"
    st, camp = call("POST", "/campaigns", {"name": f"Weekly digest {dt.date.today().isoformat()}", "type": "regular", "groups": [g["id"]],
                                              "emails": [{"subject": subject, "from_name": name, "from": frm, "content": body}]})
    print("create campaign:", st, camp.get("error", ""))
    if st in (200, 201):
        st, res = call("POST", f"/campaigns/{camp['data']['id']}/schedule", {"delivery": "instant"})
        print("send:", st, res.get("error", ""))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    {"check": check, "preview": lambda: digest(False), "send": lambda: digest(True)}[cmd]()
