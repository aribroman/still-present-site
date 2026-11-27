"""Hub meeting sources, round 2 (part 2): OA and GA official meeting finders. Weekly refresh (several requests each).
Robots.txt checked 2026-11-02: oa.org and gamblersanonymous.org allow these paths."""
import re, json, html as _html
from ._http import get_text, get

BR = {'User-Agent': 'Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Mobile Safari/537.36 (Still Present Hub meeting cache; contact hello@tab.bot)'}
DAYS = {'sunday': 0, 'monday': 1, 'tuesday': 2, 'wednesday': 3, 'thursday': 4, 'friday': 5, 'saturday': 6}
def clean(s): return re.sub(r'\s+', ' ', _html.unescape(re.sub(r'<[^>]+>', ' ', str(s or '')))).strip()
def t24(s):
    m = re.match(r'\s*(\d{1,2}):(\d{2})\s*([AP])', (s or '').upper())
    return f'{int(m.group(1)) % 12 + (12 if m.group(3) == "P" else 0):02d}:{m.group(2)}' if m else None

SOURCES = [
  {'key': 'oa', 'name': 'Overeaters Anonymous (oa.org Find a Meeting)', 'program': 'OA', 'scope': 'local', 'ttl_days': 7,
   'page': 'https://oa.org/find-a-meeting/', 'feed': 'https://oa.org/wp-json/oa-meetings/v1/meetings_search'},
  {'key': 'ga', 'name': 'Gamblers Anonymous (gamblersanonymous.org USA meetings, Florida)', 'program': 'GA', 'scope': 'local', 'ttl_days': 7,
   'page': 'https://gamblersanonymous.org/usa-meetings/?state=florida', 'feed': 'https://gamblersanonymous.org/usa-meetings/?state=florida&paged=N'},
]
CENTERS = [(25.77, -80.19), (26.12, -80.14), (26.36, -80.10), (26.70, -80.06)]   # Miami, Fort Lauderdale, Boca, West Palm: 25 mi each covers the 3 counties

def oa():
    seen, out = set(), []
    for lat, lng in CENTERS:
        body = json.dumps({'paged': 1, 'tzdb': 'America/New_York', 'meeting_type': 'in_person', 'lat': str(lat), 'longit': str(lng), 'distance': '25', 'day': '', 'per_page': 200}).encode()
        j = json.loads(get('https://oa.org/wp-json/oa-meetings/v1/meetings_search', data=body, headers=dict(BR, **{'Content-Type': 'application/json'}), timeout=40))
        for row in re.split(r'(?=<div class="meeting-results__tr meeting-results__tr--publish")', j.get('html', ''))[1:]:
            num = re.search(r'meeting-number" role="cell">.*?<span class="notranslate">(\d+)</span>', row, re.S)
            tm = re.search(r'time-day-time"><strong>([\d:]+)<span[^>]*>([AP]M)', row); dy = re.search(r'time-day-day[^>]*>(\w+)<', row)
            if not (num and tm and dy) or num.group(1) in seen or dy.group(1).lower() not in DAYS: continue
            seen.add(num.group(1))
            name = clean((re.search(r'meeting-results__name-link"[^>]*>(.*?)</a>', row, re.S) or [None, ''])[1])
            meta = re.search(r'meeting-results__meta">(.*?)</div>', row, re.S)
            parts = [clean(x) for x in re.split(r'<br\s*/?>', meta.group(1))] if meta else []
            street = parts[0] if parts else ''; cz = parts[1] if len(parts) > 1 else ''
            if not re.search(r'\d', street): continue                      # no street address published
            zz = re.findall(r'\b(\d{5})\b', cz); z = zz[-1] if zz else None; city = cz.split(',')[0].strip()
            topics = clean((re.search(r'<strong>Topics:</strong>(.*?)</div>', row, re.S) or [None, ''])[1])
            hyb = 'hybrid' if re.search(r'type--(hybrid|online)', row) and 'face-to-face' in row else 'in'
            lang = clean((re.search(r'meeting-lang">(.*?)<', row) or [None, ''])[1])
            out.append({'id': f'oa-{num.group(1)}', 'prog': 'OA', 'name': name or 'OA meeting', 'day': DAYS[dy.group(1).lower()], 'time': t24(tm.group(1) + ' ' + tm.group(2)),
                        'att': hyb, 'loc': name, 'addr': ', '.join(x for x in [street, city, 'FL ' + (z or '')] if x).strip(), 'city': city, 'zip': z,
                        'tags': ['spanish'] if lang.lower().startswith('span') else [], 'notes': ('Topics: ' + topics)[:200] if topics else None,
                        'url': f'https://oa.org/meetings/{num.group(1)}/', 'src': 'oa'})
    return out

def ga():
    out, seen = [], set()
    for page in range(1, 30):
        html = get_text(f'https://gamblersanonymous.org/usa-meetings/?city&state=florida&zipcode&radius&term=147&weekday&country&paged={page}', timeout=40, headers=BR)
        items = re.findall(r"<a href='(https://gamblersanonymous\.org/find-a-meeting/[^']+)'><div[^>]*><h4>(.*?)</h4><p[^>]*>Location:(.*?)</p><p>Time:(.*?)</p><div>(.*?)</div>", html, re.S)
        if not items: break
        for url, title, loc, tm, notes in items:
            if url in seen: continue
            seen.add(url)
            title = clean(title); loc = clean(loc).replace(', United States', ''); notes = clean(notes)
            md = re.search(r'-\s*(Sunday|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday)\s*$', title, re.I)
            if not md: continue
            zz = re.findall(r'\b(\d{5})\b', loc); z = zz[-1] if zz and zz[-1] != re.match(r'\s*(\d*)', loc).group(1) else None
            mc = re.search(r',\s*([^,]+),\s*Florida', loc)
            t0 = t24(clean(tm).split('-')[0])
            online = bool(re.search(r'(?i)zoom|online|virtual', title + ' ' + loc + ' ' + notes)) and not re.search(r'\d{2,5}\s+\w', loc)
            out.append({'id': 'ga-' + url.rstrip('/').rsplit('/', 1)[-1], 'prog': 'GA', 'name': title[:md.start()].strip(' -'), 'day': DAYS[md.group(1).lower()], 'time': t0,
                        'end': t24(clean(tm).split('-')[1]) if '-' in tm else None, 'att': 'online' if online else 'in', 'addr': '' if online else loc, 'city': mc.group(1).strip() if mc else '',
                        'zip': z, 'tags': ['closed'] if 'closed' in notes.lower() else (['open'] if 'open meeting' in notes.lower() else []), 'notes': notes[:200] or None, 'url': url, 'src': 'ga'})
    return out

def fetch(key):
    if key == 'oa': return oa()
    if key == 'ga': return ga()
    raise KeyError(key)

if __name__ == '__main__':
    for s in SOURCES:
        rows = fetch(s['key']); print(s['key'], len(rows)); [print('   ', r) for r in rows[:2]]
