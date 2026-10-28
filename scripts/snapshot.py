"""Fetch each venue's what's-on page in a real browser and save the HTML.

Stage 1 of the collector: this only saves raw pages (snapshots/<slug>-<n>.html)
and a report of what happened, so the page readers can be written against the
real markup.
"""
import json, pathlib, re, sys, time
from playwright.sync_api import sync_playwright

root = pathlib.Path(__file__).resolve().parent.parent
out = root / "snapshots"
out.mkdir(exist_ok=True)
NEW = len(sys.argv) > 1 and sys.argv[1] in ("new", "retry")
RETRY = len(sys.argv) > 1 and sys.argv[1] == "retry"
venues = json.loads((root / ("venues_new.json" if NEW else "venues.json")).read_text())["venues"]

if RETRY:
    venues = [v for v in venues if v.get("retry")]


def slim(html):
    """Bulk run: drop scripts (except data blocks), styles and svg so 200 pages stay small."""
    html = re.sub(r"<script\b(?![^>]*(?:ld\+json|application/json))[^>]*>.*?</script>", "", html, flags=re.S | re.I)
    html = re.sub(r"<(style|svg|noscript)\b.*?</\1>", "", html, flags=re.S | re.I)
    return html
report = []

with sync_playwright() as p:
    browser = p.chromium.launch()
    ctx = browser.new_context(
        user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        viewport={"width": 1280, "height": 900},
        locale="en-GB",
    )
    for v in venues:
        for i, url in enumerate(v["urls"], 1):
            entry = {"venue": v["name"], "url": url, "file": None, "status": None, "error": None, "bytes": 0}
            page = ctx.new_page()
            seen = []
            if v.get("js"):
                def on_resp(r, seen=seen):
                    ct = r.headers.get("content-type", "")
                    if "json" in ct or "api" in r.url.lower():
                        item = {"url": r.url, "status": r.status, "type": ct}
                        noisy = re.search(r"google|doubleclick|braze|termly|ketch|permutive|ad\.gt|facebook|analytics|hotjar|cookie|consent", r.url)
                        if "json" in ct and r.status == 200 and not noisy:
                            try:
                                item["body"] = r.text()[:400000]
                            except Exception:
                                pass
                        seen.append(item)
                page.on("response", on_resp)
            try:
                resp = page.goto(url, wait_until="domcontentloaded", timeout=30000 if NEW else 45000)
                entry["status"] = resp.status if resp else None
                try:
                    page.wait_for_load_state("networkidle", timeout=6000 if NEW else 20000)
                except Exception:
                    pass
                # scroll to trigger lazy-loaded lists
                for _ in range(3 if NEW else 6):
                    page.mouse.wheel(0, 2500)
                    time.sleep(0.7)
                if v.get("js"):
                    time.sleep(8)
                if v.get("js"):
                    for n, fr in enumerate([f for f in page.frames if f != page.main_frame], 1):
                        try:
                            fh = fr.content()
                            if len(fh) > 2000 and "googletagmanager" not in fr.url:
                                (out / f"{v['slug']}-frame-{n}.html").write_text(fh, encoding="utf-8")
                                print("  frame", n, fr.url[:100], len(fh), flush=True)
                        except Exception as e:
                            print("  frame error", str(e)[:100], flush=True)
                html = page.content()
                if NEW:
                    html = slim(html)
                name = f"{v['slug']}-{i}.html"
                (out / name).write_text(html, encoding="utf-8")
                entry["file"] = name
                entry["bytes"] = len(html)
                entry["final_url"] = page.url
            except Exception as e:
                entry["error"] = re.sub(r"\s+", " ", str(e))[:300]
            finally:
                if seen:
                    (out / f"{v['slug']}-network.json").write_text(json.dumps(seen[:60], indent=1))
                    for n, item in enumerate([s for s in seen if s.get("body")][:5], 1):
                        (out / f"{v['slug']}-api-{n}.json").write_text(item["body"], encoding="utf-8")
                page.close()
            print(entry, flush=True)
            report.append(entry)
    browser.close()

(out / ("_report_new.json" if NEW else "_report.json")).write_text(json.dumps(report, indent=1))
failed = [r for r in report if not r["file"]]
print(f"{len(report) - len(failed)} pages saved, {len(failed)} failed")
