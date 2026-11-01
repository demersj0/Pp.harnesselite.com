#!/usr/bin/env python3
"""One stable random complete current-day track sample, linking to original reports."""
import base64
from datetime import datetime
from html import escape
from html.parser import HTMLParser
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
from urllib.parse import quote, unquote, urljoin, urlsplit
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

SOURCE_REPO = 'demersj0/Odds.harnesselite.com'
SOURCE_ORIGIN = 'https://odds.harnesselite.com/'
TIMEZONE = 'America/New_York'
TRACK_NAMES = {
    'BANG': 'Bangor Raceway', 'BTVA': 'Batavia Downs',
    'CHRTN': 'Red Shores Charlottetown', 'CNML': 'Century Mile',
    'CUMB': 'First Tracks Cumberland', 'DTN': 'Dayton Raceway',
    'FLMD': 'Flamboro Downs', 'HOP': "Harrah's Hoosier Park",
    'INVRN': 'Inverness Raceway', 'LEAM': 'Leamington Raceway',
    'LON': 'Western Fair Raceway', 'M': 'Meadowlands', 'MEA': 'The Meadows',
    'MR': 'Monticello Raceway', 'NFLD': 'Northfield Park',
    'PCD': 'Pocono Downs', 'PHL': "Harrah's Philadelphia", 'PRC': 'Plainridge Park',
    'RCR': 'Rosecroft Raceway', 'STGA': 'Saratoga Casino Hotel',
    'TRRVS': 'Hippodrome Trois-Rivières', 'TRURO': 'Truro Raceway',
    'VD': 'Vernon Downs', 'WBSB': 'Woodbine Mohawk Park', 'YR': 'Yonkers Raceway',
}


class TrackParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.cards = []
        self.depth = 0
        self.card = None
        self.heading = False
        self.anchor = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'div':
            if self.card is not None:
                self.depth += 1
            elif 'track-card' in attrs.get('class', '').split():
                self.card = {'heading': '', 'links': []}
                self.depth = 1
        if self.card is not None:
            if tag == 'h3': self.heading = True
            if tag == 'a': self.anchor = {'href': attrs.get('href', ''), 'label': ''}

    def handle_data(self, data):
        if self.card is not None and self.heading: self.card['heading'] += data
        if self.anchor is not None: self.anchor['label'] += data

    def handle_endtag(self, tag):
        if tag == 'h3': self.heading = False
        if tag == 'a' and self.anchor is not None:
            if self.card is not None: self.card['links'].append(self.anchor)
            self.anchor = None
        if tag == 'div' and self.card is not None:
            self.depth -= 1
            if self.depth == 0:
                self.cards.append(self.card)
                self.card = None


def github_json(path):
    headers = {'Accept': 'application/vnd.github+json', 'User-Agent': 'Harness-Elite-Free-Sample'}
    token = os.environ.get('GITHUB_TOKEN') or os.environ.get('GITHUB_ACCESS_TOKEN')
    if token: headers['Authorization'] = 'Bearer ' + token
    request = Request('https://api.github.com/repos/' + SOURCE_REPO + path, headers=headers)
    with urlopen(request, timeout=35) as response:
        return json.load(response)


def eligible_cards(html, index_path, paths, race_date):
    parser = TrackParser()
    parser.feed(html)
    date_code = race_date.replace('-', '')
    result = {}
    for card in parser.cards:
        heading = card['heading'].strip()
        match = re.fullmatch(r'([A-Z0-9]{1,8})(?:\s*[-–:]\s*.*)?', heading)
        if not match: continue
        code = match.group(1)
        if code in {'ALL', 'OVERALL', 'TOTAL'}: continue
        required = {
            'Tip Sheet': re.compile(rf'TipSheet_{re.escape(code)}_{date_code}\.html', re.I),
            'LeadThreatIndex™': re.compile(rf'{re.escape(code)}_LeadThreatIndex_{date_code}\.pdf', re.I),
            'Racecards Intelligence™': re.compile(rf'Racecards_Intelligence_Report_{date_code}_Readable_v\d+_{re.escape(code)}\.pdf', re.I),
        }
        links = {}
        invalid = False
        for anchor in card['links']:
            href = anchor['href'].strip()
            absolute = urljoin(SOURCE_ORIGIN + quote(index_path, safe='/'), href)
            parsed = urlsplit(absolute)
            if parsed.scheme != 'https' or parsed.netloc.lower() != 'odds.harnesselite.com':
                invalid = True
                break
            path = unquote(parsed.path).lstrip('/')
            filename = PurePosixPath(path).name
            kind = next((label for label, pattern in required.items() if pattern.fullmatch(filename)), None)
            if kind:
                if path not in paths or '..' in PurePosixPath(path).parts:
                    invalid = True
                    break
                links[kind] = {'label': kind, 'href': absolute, 'source_path': path}
        if not invalid and len(links) == 3:
            result[code] = {'track': code, 'track_name': TRACK_NAMES.get(code, code),
                            'links': [links[kind] for kind in required]}
    return result


def load_source(race_date):
    head = github_json('/git/ref/heads/main')['object']['sha']
    tree = github_json('/git/trees/' + head + '?recursive=1')
    if tree.get('truncated'): raise RuntimeError('Source tree incomplete; refusing partial selection')
    paths = {entry['path']: entry for entry in tree['tree'] if entry['type'] == 'blob'}
    index_path = race_date + '/index.html'
    if index_path not in paths:
        return {}, {'reason': 'current_day_index_missing', 'index_path': index_path}
    blob = github_json('/git/blobs/' + paths[index_path]['sha'])
    html = base64.b64decode(blob['content']).decode('utf-8-sig')
    candidates = eligible_cards(html, index_path, paths, race_date)
    method = 'regular_index'
    if not candidates:
        # A daily index can accidentally retain yesterday's template. Never follow
        # stale links: reconstruct only complete current-day sets in THIS folder.
        date_code = race_date.replace('-', '')
        codes = sorted({m.group(1) for path in paths
                        if path.startswith(race_date + '/')
                        and '/' not in path[len(race_date) + 1:]
                        and (m := re.fullmatch(r'TipSheet_([A-Z0-9]{1,8})_' + date_code + r'\.html', PurePosixPath(path).name))})
        synthetic_cards = []
        for code in codes:
            reports = [race_date + '/' + f'TipSheet_{code}_{date_code}.html',
                       race_date + '/' + f'{code}_LeadThreatIndex_{date_code}.pdf']
            intelligence = sorted(path for path in paths if re.fullmatch(
                re.escape(race_date) + r'/Racecards_Intelligence_Report_' + date_code + r'_Readable_v\d+_' + re.escape(code) + r'\.pdf', path))
            if intelligence: reports.append(intelligence[-1])
            if len(reports) != 3 or not all(path in paths for path in reports): continue
            anchors = ''.join(f'<a href="{escape(SOURCE_ORIGIN + quote(path, safe="/"), quote=True)}">Report</a>' for path in reports)
            synthetic_cards.append(f'<div class="track-card"><h3>{code}</h3>{anchors}</div>')
        candidates = eligible_cards(''.join(synthetic_cards), index_path, paths, race_date)
        method = 'verified_current_day_files' if candidates else 'regular_index'
    return candidates, {'reason': 'ready' if candidates else 'no_complete_current_day_track_blocks',
                        'index_path': index_path, 'source_commit': head, 'source_method': method}


def render_daily_sample(root, race_date=None, source_loader=load_source, chooser=secrets.choice):
    root = Path(root)
    race_date = race_date or datetime.now(ZoneInfo(TIMEZONE)).date().isoformat()
    long_date = datetime.fromisoformat(race_date).strftime('%B %-d, %Y')
    data_dir = root / 'data'
    data_dir.mkdir(parents=True, exist_ok=True)
    state_file = data_dir / 'free_sample_selections.json'
    state = json.loads(state_file.read_text()) if state_file.exists() else {'selections': {}}
    try:
        candidates, evidence = source_loader(race_date)
        previous = state['selections'].get(race_date)
        if previous:
            chosen = candidates.get(previous['track'])
        else:
            chosen = candidates[chooser(sorted(candidates))] if candidates else None
        if chosen:
            selection = {'date': race_date, **chosen,
                         'source_index': SOURCE_ORIGIN + evidence['index_path']}
            state['selections'][race_date] = selection
            state_file.write_text(json.dumps(state, indent=2, ensure_ascii=False) + '\n')
            status = {'date': race_date, 'status': 'awaiting_public_access', 'track': chosen['track'],
                      'source_index': selection['source_index'], 'source_method': evidence.get('source_method', 'regular_index')}
            links = ''.join(f'<a href="{escape(item["href"], quote=True)}" target="_blank" rel="noopener noreferrer">{escape(item["label"])}</a>' for item in chosen['links'])
            block = f'''<section id="todays-free-sample" class="notice" style="margin-top:24px;border:2px solid #7db8ff">
<h2>Today's Free Sample: {escape(chosen['track_name'])} ({escape(chosen['track'])}), {long_date}</h2>
<p>One complete track block, randomly selected for today. This pick stays the same all day.</p>
<p><strong>Public access pending:</strong> These source reports currently require a member login. Free public access has not yet been enabled.</p>
<div class="track-card"><h3><span>{escape(chosen['track'])}</span></h3>{links}</div>
<p>These three links open the original reports at odds.harnesselite.com. No premium report files are copied to this teaser site. Applicable data-license requirements still apply.</p>
</section>'''
        else:
            status = {'date': race_date, 'status': 'waiting', 'reason': 'selected_track_not_currently_complete' if previous else evidence['reason']}
            block = f'''<section id="todays-free-sample" class="notice" style="margin-top:24px">
<h2>Today's Free Sample: {long_date}</h2>
<p>Today's complete free sample is not ready yet. It will appear automatically after the current-day regular index and all three reports are available.</p>
</section>'''
    except Exception as exc:
        # Do not present yesterday's choice or stale URLs as today's free sample.
        status = {'date': race_date, 'status': 'waiting', 'reason': 'source_temporarily_unavailable'}
        print('Free sample source check failed:', type(exc).__name__)
        block = f'''<section id="todays-free-sample" class="notice" style="margin-top:24px">
<h2>Today's Free Sample: {long_date}</h2>
<p>We are checking today's reports. Please check back shortly for today's full sample.</p>
</section>'''
    (data_dir / 'free_sample_status.json').write_text(json.dumps(status, indent=2) + '\n')
    print('Daily free sample:', json.dumps(status))
    return block
