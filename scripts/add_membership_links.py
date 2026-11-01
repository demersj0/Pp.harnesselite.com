#!/usr/bin/env python3
"""Add one Purchase Membership link to every tracked HTML page, without rewriting report content."""
from html.parser import HTMLParser
import hashlib
import json
from pathlib import Path
import re
import subprocess

MEMBERSHIP_URL = 'https://www.harnesselite.com/purchase-harness-racing-handicapping-tip-sheets-data/p/black-book-89l6j'
START = '\n<!-- HARNESS-MEMBERSHIP:START -->'
END = '<!-- HARNESS-MEMBERSHIP:END -->\n'
BANNER = START + '''
<aside id="harness-membership" aria-label="Harness Elite membership" style="box-sizing:border-box;max-width:1200px;margin:16px auto;padding:16px 20px;background:#202636;color:#eee;border:1px solid #343d50;border-radius:10px;font-family:Arial,sans-serif;text-align:center;line-height:1.5">
<a href="''' + MEMBERSHIP_URL + '''" target="_blank" rel="noopener noreferrer" style="display:inline-block;background:#171b22;color:#dbe9ff;padding:10px 18px;margin:0;border:1px solid #7db8ff;border-radius:8px;text-decoration:none;font-size:16px;font-weight:bold;line-height:1.5">Purchase Membership</a>
</aside>
''' + END
BANNER_PATTERN = re.compile(re.escape(START) + r'.*?' + re.escape(END), re.S)


def strip_membership_banner(text):
    """Reverse only our own exact marked insertion, preserving all original report bytes."""
    return BANNER_PATTERN.sub('', text)


class PageInfo(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=False)
        self.text = text
        self.lines = [0]
        self.lines += [m.end() for m in re.finditer('\n', text)]
        self.body_end = None
        self.membership_links = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag.lower() == 'body' and self.body_end is None:
            line, column = self.getpos()
            self.body_end = self.lines[line - 1] + column + len(self.get_starttag_text())
        if tag.lower() == 'a' and attrs.get('href') == MEMBERSHIP_URL:
            self.membership_links += 1


def ensure_membership_link(text):
    source = strip_membership_banner(text)
    parser = PageInfo(source)
    parser.feed(source)
    point = parser.body_end
    if point is None:
        # Support old HTML documents with an implied body, without moving their head.
        head = re.search(r'</head\s*>', source, re.I)
        doctype = re.match(r'\ufeff?\s*<!DOCTYPE[^>]*>', source, re.I)
        point = head.end() if head else doctype.end() if doctype else 0
    return source[:point] + BANNER + source[point:]


def build(root, paths=None):
    root = Path(root).resolve()
    if paths is None:
        # Include newly generated sample/track HTML as well as historical tracked pages.
        result = subprocess.run(['git', '-C', str(root), 'ls-files', '-co', '--exclude-standard', '-z'], check=True, capture_output=True)
        paths = result.stdout.decode().split('\0')
    htmls = sorted({p for p in paths if p and Path(p).suffix.lower() in {'.html', '.htm'}
                    and not p.startswith(('.git/', '.github/', 'scripts/'))})
    audit = {'generator': 'harness-membership-v1', 'membership_url': MEMBERSHIP_URL,
             'html_pages': 0, 'pages_with_membership_link': 0, 'files': {}}
    changed = 0
    for relative in htmls:
        path = (root / relative).resolve()
        if not path.is_relative_to(root) or not path.is_file() or path.is_symlink():
            continue
        original = path.read_bytes()
        try:
            text = original.decode('utf-8')
            encoding = 'utf-8'
        except UnicodeDecodeError:
            # Latin-1 maps bytes one-to-one, so legacy pages retain every original byte.
            text = original.decode('latin-1')
            encoding = 'latin-1'
        updated = ensure_membership_link(text)
        assert strip_membership_banner(updated) == strip_membership_banner(text)
        check = PageInfo(updated)
        check.feed(updated)
        if check.membership_links < 1:
            raise ValueError('Membership link missing from ' + relative)
        output = updated.encode(encoding)
        if output != original:
            path.write_bytes(output)
            changed += 1
        audit['html_pages'] += 1
        audit['pages_with_membership_link'] += 1
        audit['files'][relative] = hashlib.sha256(output).hexdigest()
    data = root / 'data'
    data.mkdir(exist_ok=True)
    (data / 'membership_link_audit.json').write_text(json.dumps(audit, indent=2) + '\n')
    print(f'Membership links verified: {audit["pages_with_membership_link"]}/{audit["html_pages"]} HTML pages; updated {changed}.')
    return audit


if __name__ == '__main__':
    build(Path(__file__).resolve().parents[1])
