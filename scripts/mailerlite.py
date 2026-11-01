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
        st, subs = call("GET", "/subscribers?limit=1")
        info["subscribers_status"] = st
        info["subscribers_total"] = (subs.get("meta") or {}).get("total")
        st, forms = call("GET", "/forms/embedded?limit=25")
        info["forms_status"] = st
        info["forms"] = [{"id": f.get("id"), "name": f.get("name"), "opted_in": f.get("opted_in_count")} for f in forms.get("data", [])] if st == 200 else forms.get("error")
    (ROOT / "mailerlite_info.json").write_text(json.dumps(info, indent=1), encoding="utf-8")
    print(json.dumps(info, indent=1))


if __name__ == "__main__":
    {"check": check}[sys.argv[1] if len(sys.argv) > 1 else "check"]()
