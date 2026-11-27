"""Hub meeting sources, round 2 (part 3): SAA telemeetings (saatalk.info, the SAA Telemeeting Intergroup site Caz named).
Public list only (members-only meetings are not shown to the public and are not read). Times are published as the next
occurrence in UTC; stored with tz 'UTC' so the app shows them in local time. Robots.txt: none. Daily refresh (one request)."""
import re, datetime as dt, html as _html
from ._http import get_text
BR = {'User-Agent': 'Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Mobile Safari/537.36 (Still Present Hub meeting cache; contact hello@tab.bot)'}
def clean(s): return re.sub(r'\s+', ' ', _html.unescape(re.sub(r'<[^>]+>', ' ', str(s or '')))).strip()
SOURCES = [{'key': 'saa_rule62', 'name': 'Rule 62 SAA (rule62saa.com, men-only online meetings)', 'program': 'SAA', 'scope': 'online', 'ttl_days': 7,
            'page': 'https://www.rule62saa.com/meetings/', 'feed': 'https://www.rule62saa.com/meetings/'},
           {'key': 'saa_tele', 'name': 'SAA Telemeeting Intergroup (saatalk.info)', 'program': 'SAA', 'scope': 'online', 'ttl_days': 1,
            'page': 'https://saatalk.info/us/meetings', 'feed': 'https://saatalk.info/us/meetings'}]
DAB = ['SUN', 'MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT']
def rule62():
    page = get_text('https://www.rule62saa.com/meetings/', timeout=40, headers=BR)
    text = re.sub(r'(?i)<br\s*/?>|</(p|div|h\d|li)>', '\n', page)
    lines = [clean(x) for x in re.sub(r'<[^>]+>', ' ', text).split('\n') if clean(x)]
    out = []
    for i, x in enumerate(lines):
        m = re.match(r'^(DAILY|[A-Z]{3})(?:\s*-\s*([A-Z]{3}))?\s*/\s*(\d{1,2})(?::(\d{2}))?\s*(AM|PM)', x.upper())
        if not m or i + 1 >= len(lines): continue
        if m.group(1) == 'DAILY': days = list(range(7))
        elif m.group(1) in DAB:
            a = DAB.index(m.group(1)); b = DAB.index(m.group(2)) if m.group(2) in DAB else a
            days = list(range(a, b + 1)) if b >= a else list(range(a, 7)) + list(range(0, b + 1))
        else: continue
        h = int(m.group(3)) % 12 + (12 if m.group(5) == 'PM' else 0); tm = f'{h:02d}:{m.group(4) or "00"}'
        name = lines[i + 1].title()
        for d in days:
            out.append({'id': f'saa_rule62-{re.sub(r"[^a-z0-9]+", "-", name.lower())}-{d}', 'prog': 'SAA', 'name': 'Rule 62: ' + name, 'day': d, 'time': tm, 'tz': 'America/New_York',
                        'att': 'online', 'tags': ['men', 'secular'], 'notes': 'Men only. Registered Zoom login required (see the meeting page).', 'url': 'https://www.rule62saa.com/meetings/', 'src': 'saa_rule62'})
    return out
def fetch(key):
    if key == 'saa_rule62': return rule62()
    page = get_text('https://saatalk.info/us/meetings', timeout=40, headers=BR)
    out, seen = [], set()
    for tr in re.findall(r'<tr>(.*?)</tr>', page, re.S):
        m = re.search(r'<a href="(/meetings/meeting/(\d+))">(.*?)</a>', tr); u = re.search(r'setUTC\(\s*(\d{4}),\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+)\s*\)', tr)
        if not (m and u): continue
        st = clean((re.search(r'class="status">(.*?)</td>', tr) or [None, ''])[1])
        if st and st.lower() not in ('ongoing', ''): continue
        d = dt.datetime(*map(int, u.groups()))
        day = (d.weekday() + 1) % 7; tm = d.strftime('%H:%M')
        k = (m.group(2), day, tm)
        if k in seen: continue
        seen.add(k)
        lang = clean((re.search(r'class="language">(.*?)</td>', tr) or [None, ''])[1]); aud = clean((re.search(r'class="attendance_audience">(.*?)</td>', tr) or [None, ''])[1])
        tel = clean((re.search(r'class="telephone">(.*?)</td>', tr) or [None, ''])[1]); onl = clean((re.search(r'class="online">(.*?)</td>', tr) or [None, ''])[1])
        tags = (['spanish'] if lang.lower().startswith('espa') else []) + (['men'] if aud == 'Men' else []) + (['women'] if aud == 'Women' else []) + (['open'] if aud == 'Open' else [])
        out.append({'id': f'saa_tele-{m.group(2)}-{day}-{tm}', 'prog': 'SAA', 'name': clean(m.group(3))[:80], 'day': day, 'time': tm, 'tz': 'UTC', 'att': 'online',
                    'tags': tags, 'notes': ', '.join(x for x in [lang, ('phone' if tel == 'Yes' else ''), ('video/online' if onl == 'Yes' else '')] if x) or None,
                    'url': 'https://saatalk.info' + m.group(1), 'src': 'saa_tele'})
    return out
if __name__ == '__main__':
    for k in ('saa_rule62', 'saa_tele'): r = fetch(k); print(k, len(r)); [print(x) for x in r[:3]]
