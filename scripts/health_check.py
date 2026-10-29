"""Fail the update run (so GitHub emails the owner) when listings look broken."""
import json, pathlib, sys

h = json.loads((pathlib.Path(__file__).resolve().parent.parent / "health.json").read_text())
problems = []
if len(h["broken"]) >= max(8, h["readers"] // 10):
    problems.append(f"{len(h['broken'])} venues stopped producing shows: {', '.join(h['broken'][:15])}")
if h["shows_before"] and h["shows_now"] < 0.7 * h["shows_before"]:
    problems.append(f"show count fell from {h['shows_before']} to {h['shows_now']}")
if problems:
    print("PROBLEM:", "; ".join(problems))
    sys.exit(1)
print("Listings look healthy:", h["shows_now"], "shows;", len(h["broken"]), "venue(s) need attention")
