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
venues = json.loads((root / "venues.json").read_text())["venues"]
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
            try:
                resp = page.goto(url, wait_until="domcontentloaded", timeout=45000)
                entry["status"] = resp.status if resp else None
                try:
                    page.wait_for_load_state("networkidle", timeout=20000)
                except Exception:
                    pass
                # scroll to trigger lazy-loaded lists
                for _ in range(6):
                    page.mouse.wheel(0, 2500)
                    time.sleep(0.7)
                html = page.content()
                name = f"{v['slug']}-{i}.html"
                (out / name).write_text(html, encoding="utf-8")
                entry["file"] = name
                entry["bytes"] = len(html)
                entry["final_url"] = page.url
            except Exception as e:
                entry["error"] = re.sub(r"\s+", " ", str(e))[:300]
            finally:
                page.close()
            print(entry, flush=True)
            report.append(entry)
    browser.close()

(out / "_report.json").write_text(json.dumps(report, indent=1))
failed = [r for r in report if not r["file"]]
print(f"{len(report) - len(failed)} pages saved, {len(failed)} failed")
