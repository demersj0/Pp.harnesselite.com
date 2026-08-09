#!/usr/bin/env python3
"""Generate the root index.html from teaser files for the latest race date."""

import re
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "index.html"

PATTERNS = (
    re.compile(r"^(?P<date>\d{8})-(?P<track>[A-Za-z0-9]+)-teaser(?:tip)?\.html$", re.I),
    re.compile(r"^TeaserTip_(?P<track>[A-Za-z0-9]+)_(?P<date>\d{8})\.html$", re.I),
    re.compile(r"^(?P<track>[A-Za-z0-9]+)_TeaserTip_(?P<date>\d{8})\.html$", re.I),
)


def find_teasers():
    teasers = []
    for path in ROOT.rglob("*.html"):
        if path == OUTPUT or ".git" in path.parts:
            continue
        for pattern in PATTERNS:
            match = pattern.match(path.name)
            if match:
                teasers.append({
                    "date": match.group("date"),
                    "track": match.group("track").upper(),
                    "href": path.relative_to(ROOT).as_posix(),
                })
                break
    return teasers


def build_html(date_code, teasers):
    race_date = datetime.strptime(date_code, "%Y%m%d")
    date_long = race_date.strftime("%B %-d, %Y")
    cards = []
    for teaser in sorted(teasers, key=lambda item: (item["track"], item["href"].lower())):
        cards.append(f'''<div class="track-card">
<h3><span>{teaser["track"]}</span></h3>
<a href="{teaser["href"]}" target="_blank">Teaser Tip</a>
</div>''')

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Harness Elite Teasers – {date_long}</title>
<style>
body{{font-family:Arial;background:#0f141c;color:#eee;margin:0;padding:25px}}
.container{{max-width:1200px;margin:auto;background:#171b22;padding:30px;border-radius:14px}}
h1{{text-align:center;color:white}}
.subtitle{{text-align:center;color:#b9c7d8;margin-bottom:25px}}
.notice{{background:#202636;border:1px solid #343d50;padding:18px;border-radius:10px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:18px;margin-top:20px}}
.track-card{{background:#202636;border:1px solid #343d50;border-radius:12px;padding:18px}}
.track-card h3 span,h2{{color:#7db8ff}}
a{{display:block;background:#171b22;color:#dbe9ff;padding:10px;margin-top:10px;border-radius:8px;text-decoration:none;font-weight:bold}}
a:hover{{text-decoration:underline}}
.legal{{margin-top:30px;line-height:1.6;color:#d7d7d7}}
.footer{{text-align:center;margin-top:30px;color:#aaa}}
</style>
</head>
<body>
<div class="container">
<h1>Harness Elite Teasers – {date_long}</h1>
<div class="subtitle">Track-specific teaser selections and previews</div>
<div class="notice">
<strong>Race Date:</strong> {date_long}<br>
<strong>Available Teasers:</strong> {len(teasers)}
</div>
<h2>Teasers</h2>
<div class="grid">
{chr(10).join(cards)}
</div>
<div class="legal">
<h2>Risk Disclosure</h2>
<p>Horse racing wagering involves substantial risk and may result in the loss of some or all funds wagered. Teaser selections, rankings, projections, and other information provided by Harness Elite do not guarantee future results.</p>
<p>Users are solely responsible for their own wagering decisions and should conduct independent analysis before placing any wager.</p>
<h2>Copyright, Trademark, and Ownership Notice</h2>
<p>Harness Elite™, HarnessElite.com™, and related proprietary materials are the intellectual property of Advanced Wagering Strategies LLC d/b/a Harness Elite.</p>
</div>
<div class="footer">© {race_date.year} Advanced Wagering Strategies LLC d/b/a Harness Elite. All Rights Reserved.</div>
</div>
</body>
</html>'''


def main():
    teasers = find_teasers()
    if not teasers:
        print("No teaser files found; leaving index.html unchanged.")
        return

    latest_date = max(item["date"] for item in teasers)
    latest_teasers = [item for item in teasers if item["date"] == latest_date]
    OUTPUT.write_text(build_html(latest_date, latest_teasers), encoding="utf-8")
    print(f"Updated index.html with {len(latest_teasers)} teaser(s) for {latest_date}.")


if __name__ == "__main__":
    main()

