"""Hub meeting sources, round 2: fellowships beyond the v1 AA/NA feeds (see CONTRACT.md).
Each fetch reads the fellowship's or intergroup's OWN public page/feed. Robots.txt checked 2026-11-02 for every host below
(none disallows these paths). Browser UA used only because some hosts serve bots a stripped page; one request per source per run."""
import re, json, html as _html
from ._http import get_text, get_json

BR = {'User-Agent': 'Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Mobile Safari/537.36 (Still Present Hub meeting cache; contact hello@tab.bot)'}
TAG = {'O': 'open', 'C': 'closed', 'BE': 'beginners', 'B': 'literature', 'BB': 'literature', 'SP': 'speaker', 'ST': 'step', 'W': 'women', 'M': 'men', 'w': 'women', 'm': 'men',
       'Y': 'young', 'YP': 'young', 'LGBTQ': 'lgbtq', 'G': 'lgbtq', 'L': 'lgbtq', 'gay': 'lgbtq', 'S': 'spanish', 'SH': 'spanish', 'X': 'wheelchair', 'MED': 'meditation', 'ME': 'meditation',
       'LIT': 'literature', 'LT': 'literature', 'A': 'secular', 'AG': 'secular', 'ASL': 'asl', 'D': 'discussion', 'NEW': 'beginners', 'BG': 'beginners', 'SS': 'step', 'STR': 'step'}
DAYS = {'sunday': 0, 'monday': 1, 'tuesday': 2, 'wednesday': 3, 'thursday': 4, 'friday': 5, 'saturday': 6}

def clean(s, n=None):
    s = re.sub(r'\s+', ' ', _html.unescape(str(s or ''))).strip()
    return (s[:n - 1] + '…') if n and len(s) > n else s
def t24(s):
    m = re.match(r'\s*(\d{1,2})(?::(\d{2}))?\s*([ap])\.?\s*m?', (s or '').lower())
    if m:
        h = int(m.group(1)) % 12 + (12 if m.group(3) == 'p' else 0); return f'{h:02d}:{m.group(2) or "00"}'
    if re.match(r'\s*(12\s*)?noon', (s or '').lower()): return '12:00'
    if re.match(r'\s*(12\s*)?midnight', (s or '').lower()): return '00:00'
    m = re.match(r'\s*(\d{1,2}):(\d{2})', s or '')
    return f'{int(m.group(1)):02d}:{m.group(2)}' if m else None
def city_zip(addr):
    m = re.search(r',\s*([^,]+),\s*FL\s*(\d{5})?', addr or '')
    return (m.group(1).strip(), m.group(2)) if m else ('', None)

SOURCES = [
  {'key': 'aa_miami', 'name': 'Miami-Dade Intergroup of AA (public meeting list page)', 'program': 'AA', 'scope': 'local', 'ttl_days': 1,
   'page': 'https://aamiamidade.org/meetings', 'feed': 'https://aamiamidade.org/meetings?tsml-day=any'},
  {'key': 'aa_broward', 'name': 'Broward County Intergroup of AA (public meeting search page)', 'program': 'AA', 'scope': 'local', 'ttl_days': 1,
   'page': 'https://aabroward.org/locations/', 'feed': 'https://aabroward.org/locations/'},
  {'key': 'rd', 'name': 'Recovery Dharma (official meeting finder)', 'program': 'RD', 'scope': 'both', 'ttl_days': 1,
   'page': 'https://recoverydharma.org/meetings/', 'feed': 'https://recoverydharma.org/wp-admin/admin-ajax.php?action=meetings'},
  {'key': 'cma', 'name': 'Crystal Meth Anonymous (official meeting finder)', 'program': 'CMA', 'scope': 'both', 'ttl_days': 1,
   'page': 'https://www.crystalmeth.org/meetings/', 'feed': 'https://www.crystalmeth.org/wp-admin/admin-ajax.php?action=meetings'},
  {'key': 'sa_se', 'name': 'Sexaholics Anonymous Southeast Region (SASERA meeting list)', 'program': 'SA', 'scope': 'local', 'ttl_days': 7,
   'page': 'https://sasera.org/meetings/', 'feed': 'https://sasera.org/meetings/?tsml-day=any'},
  {'key': 'alanon_sfl', 'name': 'Al-Anon Florida South Area 10 (district meeting pages)', 'program': 'Al-Anon', 'scope': 'local', 'ttl_days': 7,
   'page': 'https://www.southfloridaal-anon.org/', 'feed': 'https://www.southfloridaal-anon.org/meetings/'},
]

# ---------- 12 Step Meeting List sites: JSON feed, or the public HTML page when the JSON feed is restricted ----------
def tsml_json(key, url, prog):
    out = []
    for m in get_json(url, timeout=60, headers=BR):
        att = {'in_person': 'in', 'online': 'online', 'hybrid': 'hybrid'}.get(m.get('attendance_option') or 'in_person')
        if not att or m.get('day') in (None, '') or not m.get('time'): continue
        types = m.get('types') or []
        if 'TC' in types and att == 'in': continue
        addr = clean(m.get('formatted_address')).replace(', USA', ''); city, z = city_zip(addr)
        try: lat, lng = round(float(m['latitude']), 5), round(float(m['longitude']), 5)
        except Exception: lat = lng = None
        if att == 'online' or m.get('approximate') == 'yes': lat = lng = None
        out.append({'id': f"{key}-{m.get('id') or m.get('slug')}", 'prog': prog, 'name': clean(m.get('name'), 80), 'day': int(m['day']), 'time': t24(m['time']),
                    'end': t24(m.get('end_time')), 'tz': m.get('timezone') or None, 'att': att, 'loc': clean(m.get('location'), 80) if att != 'online' else '',
                    'addr': addr if att != 'online' else '', 'city': city, 'zip': z, 'lat': lat, 'lng': lng,
                    'tags': sorted({TAG[t] for t in types if t in TAG}), 'join': clean(m.get('conference_url')) or None, 'phone': clean(m.get('conference_phone')) or None,
                    'notes': clean(' '.join(x for x in [m.get('notes'), m.get('location_notes')] if x), 200) or None, 'url': m.get('url'), 'src': key})
    return out

def tsml_html(key, url, prog):
    page = get_text(url, timeout=60, headers=BR)
    j = page.find('var locations = ')
    if j < 0: raise RuntimeError('no meeting data on the page')
    locs, _ = json.JSONDecoder().raw_decode(page[j + len('var locations = '):])
    att = {}
    for m in re.finditer(r'<tr class="([^"]*)">.*?<td class="name".*?<a href="([^"?]+)', page, re.S):
        a = re.search(r'attendance-(\w+)', m.group(1)); att[m.group(2).rstrip('/')] = a.group(1) if a else 'in_person'
    out = []
    for lid, L in locs.items():
        addr = clean(L.get('formatted_address')).replace(', USA', ''); city, z = city_zip(addr)
        for m in L.get('meetings', []):
            a = {'in_person': 'in', 'online': 'online', 'hybrid': 'hybrid'}.get(att.get(m['url'].rstrip('/'), 'in_person'))
            if a is None: continue                                   # inactive / temporarily closed
            types = m.get('types') or []
            out.append({'id': f"{key}-{m['url'].rstrip('/').rsplit('/', 1)[-1]}-{m['day']}-{t24(m['time'])}", 'prog': prog, 'name': clean(m['name'], 80),
                        'day': int(m['day']), 'time': t24(m['time']), 'att': a, 'loc': clean(L.get('name'), 80) if a != 'online' else '',
                        'addr': addr if a != 'online' else '', 'city': city, 'zip': z,
                        'lat': round(L['latitude'], 5) if a != 'online' and L.get('latitude') else None, 'lng': round(L['longitude'], 5) if a != 'online' and L.get('longitude') else None,
                        'tags': sorted({TAG[t] for t in types if t in TAG}), 'url': m['url'], 'src': key})
    return out

# ---------- Broward AA: one public page lists every meeting with a Sun..Sat grid ----------
def broward():
    page = get_text('https://aabroward.org/locations/', timeout=60, headers=BR)
    out = []
    for blk in re.finditer(r"<div class='single-meeting' id='(\d+)'[^>]*data-meeting-name='([^']*)'>(.*?)</table></div>", page, re.S):
        mid, name, body = blk.group(1), clean(blk.group(2)), blk.group(3)
        st = re.search(r"status-inline ([a-z-]+)-meeting", body); st = st.group(1) if st else 'in-person'
        a = {'in-person': 'in', 'online': 'online', 'hybrid': 'hybrid'}.get(st, 'in')
        ad = re.search(r"<div class='meeting-address[^']*'>(.*?)</div>", body, re.S); parts = [clean(x) for x in clean(ad.group(1) if ad else '').split('|')]
        loc_street = parts[0] if parts else ''; city = parts[1] if len(parts) > 1 else ''; z = parts[3] if len(parts) > 3 and re.match(r'\d{5}$', parts[3]) and parts[3] != '00000' else None
        loc, street = (loc_street.split(',', 1) + [''])[:2] if ',' in loc_street else ('', loc_street)
        addr = ', '.join(x for x in [street.strip(), city, 'FL' + (' ' + z if z else '')] if x) if a != 'online' and 'online only' not in loc_street.lower() else ''
        for row in re.finditer(r"<tr class='time-slot' data-time='(\d\d:\d\d):\d\d'>(.*?)</tr>", body, re.S):
            for d in re.finditer(r'<div class="day-column" data-day="(\w+)">(.*?)</div>\s*</td>', row.group(2), re.S):
                types = re.findall(r'data-specific="([^"]+)"', d.group(2))
                day = DAYS.get(d.group(1).lower())
                if day is None: continue
                out.append({'id': f'aa_broward-{mid}-{day}-{row.group(1)}', 'prog': 'AA', 'name': name, 'day': day, 'time': row.group(1), 'att': a,
                            'loc': clean(loc, 80) if a != 'online' else '', 'addr': addr, 'city': city, 'zip': z,
                            'tags': sorted({TAG[t] for t in types if t in TAG}), 'url': 'https://aabroward.org/locations/', 'src': 'aa_broward'})
    return out

# ---------- Al-Anon Florida South Area 10: one page per district, meetings as text blocks under day headings ----------
AFG_DISTRICTS = None
def alanon():
    home = get_text('https://www.southfloridaal-anon.org/', timeout=40, headers=BR)
    links = sorted(set(re.findall(r'href="(https://www\.southfloridaal-anon\.org/meetings/district-[^"]+)"', home)))
    out = []
    for url in links:
        page = get_text(url, timeout=40, headers=BR)
        body = page[page.find('<body'):]
        body = re.sub(r'(?is)<(script|style|noscript)[^>]*>.*?</\1>', ' ', body)
        body = re.sub(r'(?i)<br\s*/?>|</(p|div|h\d|li|tr|td|section|article)>', '\n', body)
        lines = [clean(x) for x in re.sub(r'<[^>]+>', ' ', body).split('\n') if clean(x)]
        day = None; spanish = False; i = 0; found = 0
        # start after the "Jump to:" index
        try: i = next(k for k, x in enumerate(lines) if x.lower().startswith('key')) + 1
        except StopIteration: pass
        while i < len(lines):
            x = lines[i]; xl = x.lower()
            if xl in DAYS: day = DAYS[xl]; i += 1; continue
            md = re.match(r'^(sunday|monday|tuesday|wednesday|thursday|friday|saturday)\s*/\s*\w+\s*-?\s*(.*)$', x, re.I)   # Spanish list: "Saturday/Sabado- 9:00 AM ..."
            if md: day = DAYS[md.group(1).lower()]; x = md.group(2); lines[i] = x; xl = x.lower()
            if (xl.startswith('spanish') or 'reuniones en español' in xl or xl.startswith('español')) and found: spanish = True; i += 1; continue   # not the "Jump to" index
            m = re.match(r'^(\d{1,2}:\d{2}\s*[AaPp]\.?\s*[Mm]\.?|12\s*noon)\s+(.*)$', x)
            if m and day is not None:
                name = m.group(2); j = i + 1
                if j < len(lines) and re.match(r'^(AFG|Al-Anon|Alateen)\b', lines[j]) and len(lines[j]) < 20: name += ' ' + lines[j]; j += 1
                TIME_RX = r'^(\d{1,2}:\d{2}\s*[AaPp]|12\s*noon)'
                if j < len(lines) and re.match(TIME_RX, lines[j]):        # two meetings share the next address line
                    j2 = j
                    while j2 < len(lines) and re.match(TIME_RX, lines[j2]): j2 += 1
                    shared = lines[j2] if j2 < len(lines) else ''
                    zm = re.search(r'\b(3[2-4]\d{3})\b', shared)
                    out.append({'id': f"alanon_sfl-{re.sub(r'[^a-z0-9]+', '-', (name + shared[:20]).lower())[:60]}-{day}-{t24(m.group(1))}", 'prog': 'Alateen' if 'alateen' in name.lower() else 'Al-Anon',
                                'name': clean(name, 80), 'day': day, 'time': t24(m.group(1)), 'att': 'in', 'addr': shared, 'loc': '', 'city': '', 'zip': zm.group(1) if zm else None,
                                'tags': ['beginners'] if re.search(r'(?i)newcomer|beginner', name) else [], 'url': url, 'src': 'alanon_sfl'})
                    found += 1; i = j; continue
                addr = lines[j] if j < len(lines) else ''
                for extra in (1, 2):                             # address split over 2-3 lines ("Church" / "370 SW 3rd St," / "Boca Raton, Fl 33432")
                    if re.search(r'(?i)\bFL\b|florida', addr) or j + 1 >= len(lines) or re.match(r'(?i)^(notes?|location|map)\b', lines[j + 1]): break
                    if re.search(r'(?i)\bFL\b|\d{3,5}\s+\w', lines[j + 1]): j += 1; addr += ', ' + lines[j]
                    else: break
                notes = []
                k = j + 1
                while k < len(lines) and not re.match(r'^(\d{1,2}:\d{2}|12\s*noon)', lines[k]) and lines[k].lower() not in DAYS and lines[k] != 'MAP' and len(notes) < 4:
                    notes.append(lines[k]); k += 1
                online = bool(re.search(r'(?i)\bzoom\b|online|virtual|electronic', addr + ' ' + ' '.join(notes)))
                inperson = bool(re.search(r'\d{2,5}\s+\w', addr)) and not re.search(r'(?i)electronic|zoom|meeting id|reunion', addr)
                a = 'hybrid' if online and inperson else ('online' if online else 'in')
                zm = re.search(r'\b(3[2-4]\d{3})\b', addr); cm = re.search(r',\s*([A-Za-z .]+?),?\s*(?:FL|Florida)\b', addr, re.I)
                prog = 'Alateen' if 'alateen' in name.lower() else 'Al-Anon'
                tags = (['spanish'] if spanish or re.search(r'(?i)español|spanish', name) else []) + (['beginners'] if re.search(r'(?i)newcomer|beginner', name) else [])
                out.append({'id': f"alanon_sfl-{re.sub(r'[^a-z0-9]+', '-', (name + addr[:20]).lower())[:60]}-{day}-{t24(m.group(1))}", 'prog': prog,
                            'name': clean(name, 80), 'day': day, 'time': t24(m.group(1)), 'att': a, 'addr': addr if inperson else '', 'loc': '',
                            'city': cm.group(1).strip() if cm else '', 'zip': zm.group(1) if zm else None, 'tags': tags,
                            'notes': clean(' '.join(notes), 200) or None, 'url': url, 'src': 'alanon_sfl'})
                found += 1; i = k; continue
            i += 1
    return out

def fetch(key):
    if key == 'aa_miami': return tsml_html(key, 'https://aamiamidade.org/meetings?tsml-day=any', 'AA')
    if key == 'aa_broward': return broward()
    if key == 'rd': return tsml_json(key, 'https://recoverydharma.org/wp-admin/admin-ajax.php?action=meetings', 'RD')
    if key == 'cma': return tsml_json(key, 'https://www.crystalmeth.org/wp-admin/admin-ajax.php?action=meetings', 'CMA')
    if key == 'sa_se': return tsml_html(key, 'https://sasera.org/meetings/?tsml-day=any', 'SA')
    if key == 'alanon_sfl': return alanon()
    raise KeyError(key)

if __name__ == '__main__':
    import sys, time
    for s in SOURCES:
        if len(sys.argv) > 1 and s['key'] not in sys.argv[1:]: continue
        t0 = time.time()
        try: rows = fetch(s['key']); print(s['key'], len(rows), f'{time.time()-t0:.1f}s'); [print('   ', r) for r in rows[:2]]
        except Exception as e: print(s['key'], 'FAILED', repr(e))
