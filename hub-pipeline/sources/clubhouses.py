"""Hub meeting sources, round 2: South Florida recovery clubhouses (venues) and their own posted schedules.
Each clubhouse is a venue; meetings at the same street address in the fellowship feeds are tagged with it by the builder.
Robots.txt checked 2026-11-02 (none disallows these pages). Schedules change rarely: weekly refresh."""
import re, html as _html
from ._http import get_text

BR = {'User-Agent': 'Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Mobile Safari/537.36 (Still Present Hub meeting cache; contact hello@tab.bot)'}
DAYS = ['sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday']
def clean(s): return re.sub(r'\s+', ' ', _html.unescape(re.sub(r'<[^>]+>', ' ', str(s or '')))).strip()
def t24(s):
    s = (s or '').lower().strip()
    if re.match(r'(12\s*)?noon', s): return '12:00'
    m = re.match(r'(\d{1,2})(?::(\d{2}))?\s*([ap])', s)
    if not m: return None
    return f'{int(m.group(1)) % 12 + (12 if m.group(3) == "p" else 0):02d}:{m.group(2) or "00"}'
PROG = [(r'nar-?\s?anon', 'Nar-Anon'), (r'gam-?\s?anon', 'Gam-Anon'), (r'al-?\s?anon', 'Al-Anon'), (r'alateen', 'Alateen'), (r'adult child|acoa|\baca\b', 'ACA'), (r'co-?dependen|\bcoda\b', 'CoDA'), (r'cocaine|\bca\b', 'CA'),
        (r'crystal meth|\bcma\b', 'CMA'), (r'narcotics|\bna\b', 'NA'), (r'sexual compulsive|\bsca\b', 'SCA'), (r'sex (&|and) love|\bslaa\b', 'SLAA'),
        (r'sex addicts|\bsaa\b', 'SAA'), (r'sexaholics|\bsa\b', 'SA'), (r'overeaters|\boa\b', 'OA'), (r'gamblers|\bga\b', 'GA'), (r'marijuana|\bma\b', 'MA'),
        (r'recovery dharma', 'RD'), (r'smart recovery', 'SMART'), (r'anorexic|bulimic|\baba\b', 'Other'), (r'alcoholics|\baa\b|big book|step study', 'AA')]
def prog_of(*texts):
    t = ' '.join(texts).lower()
    for rx, p in PROG:
        if re.search(rx, t): return p
    return None

V = {
  'lambda_south': {'key': 'lambda_south', 'name': 'Lambda South', 'addr': '1231 E Las Olas Blvd, Fort Lauderdale, FL 33301', 'city': 'Fort Lauderdale', 'lat': 26.11943, 'lng': -80.1306, 'url': 'https://lambdasouth.com/meeting-schedule/'},
  'crossroads_club': {'key': 'crossroads_club', 'name': 'The Crossroads Club', 'addr': '1700 Lake Ida Rd, Delray Beach, FL 33445', 'city': 'Delray Beach', 'lat': 26.47175, 'lng': -80.09016, 'url': 'https://thecrossroadsclub.com/'},
  'sobe_room': {'key': 'sobe_room', 'name': 'The SoBe Room', 'addr': '1718 Bay Rd, Miami Beach, FL 33139', 'city': 'Miami Beach', 'lat': 25.79245, 'lng': -80.1439, 'url': 'https://www.thesoberoom.com/'},
  'fourth_dimension': {'key': 'fourth_dimension', 'name': 'The 4th Dimension Club', 'addr': '4425 Hollywood Blvd, Hollywood, FL 33021', 'city': 'Hollywood', 'lat': 26.01063, 'lng': -80.18785, 'url': 'https://aabroward.org/locations/4th-dimension-club/'},
  'sober_today_club': {'key': 'sober_today_club', 'name': 'Sober Today Club', 'addr': '2035 Harding St, Hollywood, FL 33020', 'city': 'Hollywood', 'lat': 26.02808, 'lng': -80.14815, 'url': 'https://www.sobertodayclub.com/'},
}
SOURCES = [
  {'key': 'club_lambda_south', 'name': 'Lambda South (clubhouse schedule)', 'program': 'Mixed', 'scope': 'local', 'ttl_days': 7, 'page': 'https://lambdasouth.com/meeting-schedule/', 'feed': 'https://lambdasouth.com/meeting-schedule/', 'venue': V['lambda_south']},
  {'key': 'club_crossroads', 'name': 'The Crossroads Club, Delray Beach (clubhouse schedule)', 'program': 'Mixed', 'scope': 'local', 'ttl_days': 7, 'page': 'https://thecrossroadsclub.com/sunday-meeting-schedule/', 'feed': 'https://thecrossroadsclub.com/<day>-meeting-schedule/', 'venue': V['crossroads_club']},
  {'key': 'club_sobe_room', 'name': 'The SoBe Room, Miami Beach (clubhouse schedule)', 'program': 'Mixed', 'scope': 'local', 'ttl_days': 7, 'page': 'https://www.thesoberoom.com/the-sobe-room-aa', 'feed': 'https://www.thesoberoom.com/the-sobe-room-aa + /sobe-room-others', 'venue': V['sobe_room']},
  # Venues whose own schedule could not be read (Facebook page / script-drawn list); their meetings come from the Broward AA list by address.
  {'key': 'club_fourth_dimension', 'name': 'The 4th Dimension Club, Hollywood (meetings from the Broward AA list)', 'program': 'Mixed', 'scope': 'local', 'ttl_days': 7, 'page': 'https://aabroward.org/locations/4th-dimension-club/', 'feed': '', 'venue': V['fourth_dimension'], 'venue_only': True},
  {'key': 'club_sober_today', 'name': 'Sober Today Club, Hollywood (meetings from the Broward AA list)', 'program': 'Mixed', 'scope': 'local', 'ttl_days': 7, 'page': 'https://www.sobertodayclub.com/friday', 'feed': '', 'venue': V['sober_today_club'], 'venue_only': True},
]

def row(key, venue, name, prog, day, time, att='in', tags=(), notes=None, url=None, join=None):
    v = V[venue]
    return {'id': f"{key}-{day}-{time}-{re.sub(r'[^a-z0-9]+', '-', name.lower())[:40]}", 'prog': prog, 'name': name[:80], 'day': day, 'time': time, 'att': att,
            'loc': v['name'], 'addr': v['addr'] if att != 'online' else '', 'city': v['city'], 'zip': re.search(r'\d{5}', v['addr']).group(0),
            'lat': v['lat'] if att != 'online' else None, 'lng': v['lng'] if att != 'online' else None, 'tags': sorted(set(tags)), 'notes': notes, 'url': url or v['url'],
            'join': join, 'venue': venue, 'src': key}

def lambda_south():
    page = get_text('https://lambdasouth.com/meeting-schedule/', timeout=40, headers=BR)
    body = re.sub(r'(?is)<(script|style)[^>]*>.*?</\1>', ' ', page)
    body = re.sub(r'(?i)<br\s*/?>|</(p|div|h\d|li|tr|section)>', '\n', body)
    lines = [clean(x) for x in body.split('\n') if clean(x)]
    out, day, prog = [], None, None
    for x in lines:
        xl = x.lower()
        if xl in DAYS: day = DAYS.index(xl); prog = None; continue
        m = re.match(r'^(\d{1,2}:\d{2}\s*[ap]m)\s*\|\s*([^|]+?)\s*(?:\(([^)]*)\))?\s*(?:\|(.*))?$', x, re.I)
        if m and day is not None:
            codes = [c.strip() for c in (m.group(3) or '').split(',')]
            att = 'online' if 'V' in codes else ('hybrid' if 'HB' in codes else 'in')
            tags = [t for c, t in (('O', 'open'), ('C', 'closed'), ('Med', 'meditation'), ('Sp', 'speaker'), ('St', 'step'), ('B', 'beginners')) if c in codes]
            p = prog or prog_of(m.group(2)) or 'Other'
            out.append(row('club_lambda_south', 'lambda_south', clean(m.group(2)), p, day, t24(m.group(1)), att, tags + ['lgbtq'], clean(m.group(4) or '')[:200] or None))
            continue
        if day is not None and not re.match(r'^\d', x) and len(x) < 50:
            p = prog_of(x)
            if p and not x.lower().startswith(('join', 'passcode', 'meeting #')): prog = p
    return out

def crossroads():
    out = []
    for d, dn in enumerate(DAYS):
        url = f'https://thecrossroadsclub.com/{dn}-meeting-schedule/'
        page = get_text(url, timeout=40, headers=BR)
        tb = re.search(r'<table[^>]*wpDataTable[^>]*>(.*?)</table>', page, re.S)
        if not tb: continue
        for tr in re.findall(r'<tr[^>]*>(.*?)</tr>', tb.group(1), re.S):
            tds = [clean(x) for x in re.findall(r'<td[^>]*>(.*?)</td>', tr, re.S)]
            if len(tds) < 5 or not t24(tds[1]): continue
            name, mtype, room = tds[3], tds[4], (tds[5] if len(tds) > 5 else '')
            p = prog_of(mtype) or prog_of(name) or 'Other'
            tags = (['women'] if re.search(r'(?i)women', name) else []) + (['men'] if re.search(r'(?i)\bmen\b', name) else [])
            out.append(row('club_crossroads', 'crossroads_club', name, p, d, t24(tds[1]), 'in', tags, ('Room ' + room) if room else None, url))
    return out

def sobe():
    out = []
    for url, default in (('https://www.thesoberoom.com/the-sobe-room-aa', 'AA'), ('https://www.thesoberoom.com/sobe-room-others', None)):
        page = get_text(url, timeout=40, headers=BR)
        tb = re.search(r'<table[^>]*>(.*?)</table>', page, re.S)
        if not tb: continue
        notyet_legend = bool(re.search(r'(?is)NOT</strong>\s*yet in person|not\s+yet\s+in\s+person', page))
        marks_readable = bool(re.search(r'(?i)background-color:\s*#?f{4}00', tb.group(1)))
        for tr in re.findall(r'<tr[^>]*>(.*?)</tr>', tb.group(1), re.S):
            cells = re.findall(r'<t[dh]([^>]*)>(.*?)</t[dh]>', tr, re.S)
            if not cells: continue
            tm = t24(clean(cells[0][1]))
            if not tm: continue
            col = 0
            for attrs, html in cells[1:]:
                span = int((re.search(r'colspan="?(\d+)', attrs) or [0, 1])[1])
                name = clean(html)
                if name and col < 7:
                    for d in range(col, min(7, col + span)):
                        p = default or prog_of(name) or 'Other'
                        tags = (['spanish'] if re.search(r'(?i)spanish|español', name) else []) + (['women'] if re.search(r'(?i)women', name) else []) + (['men'] if re.search(r"(?i)\bmen'?s\b", name) else [])
                        notes = 'On the beach at 14th St and Ocean Dr' if 'beach meeting' in name.lower() else None
                        # The schedule marks meetings "NOT yet in person" with a yellow highlight (inline background-color:#ffff00
                        # on the cell's text). Read that markup; if the legend is there but the markup can't be read, say "check".
                        att = 'in'
                        if notyet_legend and re.search(r'(?i)background-color:\s*#?f{4}00', html):
                            att = 'online'; notes = 'Not yet meeting in person at the SoBe Room (marked on its schedule). Check with the venue for how it meets.'
                        elif notyet_legend and not marks_readable:
                            notes = ((notes + '. ') if notes else '') + 'Check with venue: the schedule marks some meetings as not yet in person.'
                        out.append(row('club_sobe_room', 'sobe_room', name.rstrip('*'), p, d, tm, att, tags, notes, url))
                col += span
    return out

def fetch(key):
    if key == 'club_lambda_south': return lambda_south()
    if key == 'club_crossroads': return crossroads()
    if key == 'club_sobe_room': return sobe()
    if key in ('club_fourth_dimension', 'club_sober_today'): return []
    raise KeyError(key)

if __name__ == '__main__':
    import sys, collections
    for s in SOURCES:
        rows = fetch(s['key']); print(s['key'], len(rows), dict(collections.Counter(r['prog'] for r in rows)))
        for r in rows[:2]: print('   ', r)
