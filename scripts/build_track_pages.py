#!/usr/bin/env python3
"""Build permanent track archives from files already tracked in this repository."""
import argparse
from collections import defaultdict
from datetime import datetime
from html import escape
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
from urllib.parse import quote

PATTERNS = [
    r'^(?P<date>\d{8})-(?P<track>[A-Z0-9]{1,8})-teaser(?:tip)?\.html$',
    r'^TeaserTip_(?P<track>[A-Z0-9]{1,8})_(?P<date>\d{8})\.html$',
    r'^(?P<track>[A-Z0-9]{1,8})_TeaserTip_(?P<date>\d{8})\.html$',
    r'^TipSheet_(?P<track>[A-Z0-9]{1,8})_(?P<date>\d{8})\.html$',
    r'^(?P<track>[A-Z0-9]{1,8})_LeadThreatIndex_(?P<date>\d{8})\.pdf$',
    r'^Racecards_Intelligence_Report_(?P<date>\d{8})_Readable_v\d+_(?P<track>[A-Z0-9]{1,8})(?: - Copy)?\.pdf$',
    r'^(?P<track>[A-Z0-9]{1,8})_Race_Report_(?P<date>\d{8})\.pdf$',
    r'^(?:\d+-)?(?P<track>[A-Z0-9]{1,8})-RACE\d+-(?:PACE|TROT)\.pdf$',
]
PATTERNS = [re.compile(p, re.I) for p in PATTERNS]
EXTENSIONS = {'.html', '.pdf', '.csv', '.xlsx', '.xls', '.txt', '.zip'}
CSS = '''body{font-family:Arial,sans-serif;background:#0f141c;color:#eee;margin:0;padding:24px}main{max-width:1200px;margin:auto;background:#171b22;padding:28px;border-radius:14px}h1,h2,h3{color:#7db8ff}a{color:#dbe9ff}nav{margin-bottom:24px}nav a{margin-right:20px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:16px}.card,section{background:#202636;border:1px solid #343d50;border-radius:12px;padding:18px;margin-bottom:18px}.card a{font-size:1.3rem;font-weight:bold}li{margin:14px 0;overflow-wrap:anywhere}small,.muted{color:#b9c7d8}input{box-sizing:border-box;width:100%;padding:12px;margin:16px 0;background:#202636;color:#eee;border:1px solid #343d50;border-radius:8px}.legal{line-height:1.6;margin-top:30px}footer{text-align:center;color:#aaa;margin-top:24px}[hidden]{display:none!important}'''
LEGAL = '''<div class="legal"><h2>Risk Disclosure</h2><p>Horse racing wagering involves substantial risk and may result in the loss of some or all funds wagered. Past performance, selections, rankings, projections, and other information provided by Harness Elite do not guarantee future results. Users are solely responsible for their own wagering decisions.</p><h2>Copyright, Trademark, and Ownership Notice</h2><p>Harness Elite™, LeadThreatIndex™, Racecards Intelligence™, HarnessElite.com™, and related proprietary materials are the intellectual property of Advanced Wagering Strategies LLC d/b/a Harness Elite. Reports remain subject to applicable subscription and licensing requirements.</p></div><footer>© Advanced Wagering Strategies LLC d/b/a Harness Elite. All Rights Reserved.</footer>'''


def valid_date(code):
    try:
        return datetime.strptime(code, '%Y%m%d').strftime('%Y-%m-%d')
    except ValueError:
        return None


def classify(path, known=None):
    name = PurePosixPath(path).name
    for pattern in PATTERNS:
        m = pattern.fullmatch(name)
        if m:
            values = m.groupdict()
            return (values['track'].upper(), values.get('date')) if values['track'].upper() not in {'OVERALL', 'ALL', 'TOTAL'} else None
    # Further report types are accepted only for an independently identified code.
    for code in sorted(known or (), key=len, reverse=True):
        if re.match(re.escape(code) + r'[_-]', name, re.I):
            return code, None
    return None


def race_date(path, code):
    if code:
        return valid_date(code) or 'Undated'
    # The filename's date outranks the enclosing folder's date.
    for value in re.findall(r'(?<!\d)(\d{8})(?!\d)', PurePosixPath(path).name):
        if valid_date(value):
            return valid_date(value)
    for part in reversed(PurePosixPath(path).parts[:-1]):
        m = re.fullmatch(r'(\d{4})-(\d{1,2})-(\d{1,2})', part)
        if m:
            try:
                return datetime(*map(int, m.groups())).strftime('%Y-%m-%d')
            except ValueError:
                pass
        if re.fullmatch(r'\d{8}', part) and valid_date(part):
            return valid_date(part)
    return 'Undated'


def label(path):
    name = PurePosixPath(path).name
    low = name.lower()
    if 'teaser' in low: return 'Teaser Tip'
    if low.startswith('tipsheet_'): return 'Tip Sheet'
    if 'leadthreatindex' in low: return 'LeadThreatIndex™'
    if low.startswith('racecards_intelligence'): return 'Racecards Intelligence™'
    return name


def document(title, body):
    return f'''<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(title)} | Harness Elite</title><style>{CSS}</style></head><body><main><nav><a href="/">Latest teasers</a><a href="/tracks/">All tracks</a></nav><h1>{escape(title)}</h1>{body}{LEGAL}</main></body></html>'''


def build(root, paths):
    candidates = sorted(set(p for p in paths if not p.startswith(('.git/', '.github/', 'scripts/')) and PurePosixPath(p).suffix.lower() in EXTENSIONS and PurePosixPath(p).name.lower() != 'index.html'))
    known = {classify(p)[0] for p in candidates if classify(p)}
    tracks = defaultdict(list)
    unmatched = []
    for path in candidates:
        info = classify(path, known)
        if not info:
            unmatched.append(path)
            continue
        code, date = info
        tracks[code].append({'path':path, 'date':race_date(path, date), 'label':label(path)})
    output = root / 'tracks'
    output.mkdir(parents=True, exist_ok=True)
    manifest = {'generator':'harness-elite-track-pages-v1','tracks':dict(sorted(tracks.items())), 'unclassified_files':unmatched}
    # Retain permanent pages even if all of a track's reports have been removed.
    old = output / 'manifest.json'
    if old.exists():
        previous = json.loads(old.read_text())
        if previous.get('generator') == manifest['generator']:
            for code in previous['tracks']:
                if re.fullmatch(r'[A-Z0-9]{1,8}', code) and code not in {'OVERALL', 'ALL', 'TOTAL'}: tracks.setdefault(code, [])
    cards = []
    for code, records in sorted(tracks.items()):
        groups = defaultdict(list)
        for row in records: groups[row['date']].append(row)
        body = f'<p class="muted">{len(records)} related files. Dates are newest first. This permanent page updates automatically after repository uploads, moves, or deletions.</p><label for="search">Filter files or dates</label><input id="search" type="search" placeholder="Search filenames or dates">'
        for date in sorted(groups, key=lambda d: (d != 'Undated', d), reverse=True):
            items=[]
            for row in sorted(groups[date], key=lambda r:(r['label'],r['path'])):
                href=quote('/'+row['path'],safe='/')
                items.append(f'<li><a href="{href}" target="_blank" rel="noopener">{escape(row["label"])}</a><br><small>{escape(row["path"])}</small></li>')
            body += f'<section data-date="{escape(date)}"><h2>{escape(date)}</h2><ul>{"".join(items)}</ul></section>'
        if not records: body += '<p>No files currently available for this track.</p>'
        body += '''<script>document.getElementById('search').addEventListener('input',function(){const q=this.value.toLowerCase();document.querySelectorAll('section[data-date]').forEach(s=>{let n=0;s.querySelectorAll('li').forEach(li=>{li.hidden=!(li.textContent+' '+s.dataset.date).toLowerCase().includes(q);if(!li.hidden)n++});s.hidden=n===0})})</script>'''
        folder=output/code; folder.mkdir(exist_ok=True)
        (folder/'index.html').write_text(document(code+' Reports',body),encoding='utf-8')
        latest=max((r['date'] for r in records if r['date']!='Undated'),default='No dated files')
        cards.append(f'<div class="card"><a href="/tracks/{code}/">{code}</a><p>{len(records)} files</p><small>Latest: {escape(latest)}</small></div>')
    manifest['tracks']=dict(sorted(tracks.items()))
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    (output/'index.html').write_text(document('Track Directory',f'<p>{len(tracks)} permanent track pages. Each archive includes related files already in this repository.</p><label for="track-search">Find a track code</label><input id="track-search" type="search" placeholder="e.g. CHRTN"><div class="grid">'+''.join(cards)+'''</div><script>document.getElementById('track-search').addEventListener('input',function(){const q=this.value.toLowerCase();document.querySelectorAll('.card').forEach(c=>c.hidden=!c.querySelector('a').textContent.toLowerCase().includes(q))})</script>'''),encoding='utf-8')
    print(f'Built {len(tracks)} track pages for {sum(map(len,tracks.values()))} files; {len(unmatched)} files unclassified (see tracks/manifest.json).')
    return manifest


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);parser.add_argument('--file-manifest',type=Path)
    args=parser.parse_args();root=args.root.resolve()
    if args.file_manifest:
        paths=json.loads(args.file_manifest.read_text())
    else:
        paths=subprocess.check_output(['git','ls-files','-z'],cwd=root).decode().split('\0')
        paths=[p for p in paths if p and (root/p).is_file()]
    build(root,paths)

if __name__=='__main__':main()
