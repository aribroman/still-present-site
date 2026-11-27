#!/usr/bin/env python3
"""Still Present Hub v1 data builder.
Fetches public meeting feeds (NA: BMLT; AA: Meeting Guide / 12 Step Meeting List feeds; online AA: OIAA),
filters SoFlo Scene events to sober-friendly ones (+ Eventbrite "sober" searches), and writes compact static JSON to
center/site/hub/data/. A source that fails keeps its last good copy (raw/last_<key>.json). Run daily (see refresh.sh).
"""
import sys, os, re, json, time, datetime as dt, hashlib
from concurrent.futures import ThreadPoolExecutor
try:
    import requests
except ImportError:          # the box's system python has no requests; a tiny urllib shim covers what this script uses
    import urllib.request, urllib.parse
    class _R:
        def __init__(s, code, body): s.status_code, s.content = code, body
        def raise_for_status(s):
            if s.status_code >= 400: raise RuntimeError(f'HTTP {s.status_code}')
        def json(s): return json.loads(s.content)
    class requests:
        @staticmethod
        def get(url, params=None, headers=None, timeout=60):
            if params: url += ('&' if '?' in url else '?') + urllib.parse.urlencode(params, doseq=True)
            req = urllib.request.Request(url, headers=headers or {})
            try:
                with urllib.request.urlopen(req, timeout=timeout) as r: return _R(r.status, r.read())
            except urllib.error.HTTPError as e: return _R(e.code, e.read())

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.environ.get('HUB_OUT_DIR') or os.path.join(os.path.dirname(HERE), 'hub', 'data')
RAW = os.path.join(HERE, 'raw')
SOFLO_URLS = [
    os.environ.get('SOFLO_EVENTS_URL') or 'https://sofloscene.pages.dev/data/events.js',
    'https://raw.githubusercontent.com/aribroman/soflo-scene/main/site/data/events.js',
]
os.makedirs(OUT, exist_ok=True); os.makedirs(RAW, exist_ok=True)
UA = {'User-Agent': 'Mozilla/5.0 (Still Present Hub meeting cache; daily; +https://stillpresent.pages.dev/)'}
NOW = dt.datetime.now(dt.timezone.utc)
STAMP = NOW.strftime('%Y-%m-%dT%H:%M:%SZ')
LOG = []
def log(*a):
    s = ' '.join(str(x) for x in a); LOG.append(s); print(s, file=sys.stderr)

def get_json(url, params=None, timeout=60):
    last = None
    for i in range(3):
        try:
            r = requests.get(url, params=params, headers=UA, timeout=timeout)
            r.raise_for_status(); return r.json()
        except Exception as e:
            last = e; time.sleep(3 * (i + 1))
    raise last

def clean(s, n=None):
    s = re.sub(r'\s+', ' ', str(s or '')).strip()
    return (s[:n - 1] + '…') if n and len(s) > n else s

# ---------- meetings ----------
MEETING_SOURCES = {
  'na_sfl': {'name': 'South Florida Region of NA (BMLT, Southeast Zonal Forum server)', 'program': 'NA',
             'feed': 'https://bmlt.sezf.org/main_server/client_interface/json/?switcher=GetSearchResults&services[]=20&services[]=134&recursive=1',
             'page': 'https://sfrna.net/'},
  'aa_pbc': {'name': 'Palm Beach County Intergroup of AA', 'program': 'AA',
             'feed': 'https://aapalmbeachcounty.org/wp-admin/admin-ajax.php?action=meetings', 'page': 'https://aapalmbeachcounty.org/meetings/'},
  'aa_spbc': {'name': 'South Palm Beach County Intergroup of AA', 'program': 'AA',
              'feed': 'https://www.aainpalmbeach.org/wp-admin/admin-ajax.php?action=meetings', 'page': 'https://www.aainpalmbeach.org/meetings/'},
  'aa_online': {'name': 'Online Intergroup of AA (OIAA), online meetings', 'program': 'AA',
                'feed': 'https://data.aa-intergroup.org/6436f5a3f03fdecef8459055.json', 'page': 'https://aa-intergroup.org/meetings/'},
}
NOT_INCLUDED = [   # checked 2026-11-02 (rounds 2 and 3); each says why, so the app can say what is missing
  {'name': 'Miami-Dade Al-Anon (districts 190/200 site)', 'url': 'https://alanonsofla.org/', 'why': 'Its meeting feed is restricted; only the Area 10 district pages are read (few Miami-Dade meetings).'},
  {'name': 'Marijuana Anonymous, Nar-Anon', 'url': 'https://marijuana-anonymous.org/', 'why': 'Their meeting feeds are restricted by the fellowship; not worked around. Meetings at clubhouses are included.'},
  {'name': 'SMART Recovery online (national)', 'url': 'https://meetings.smartrecovery.org/meetings/', 'why': 'Only SMART meetings held or hosted in South Florida are read (round 3); the national online list is not.'},
  {'name': 'Celebrate Recovery online', 'url': 'https://celebraterecovery.com/weekly-online-recovery-meetings/', 'why': 'Online meeting links are sent by email after sign-up; nothing public to list.'},
  {'name': 'SLAA online, SLAA Palm Beach intergroup list', 'url': 'https://slaafws.org/onlinemeetings/', 'why': 'Round 3 reads the SLAA finder for Florida in-person meetings only; the online list and the Palm Beach intergroup\'s own list are not read yet.'},
  {'name': 'Debtors Anonymous', 'url': 'https://debtorsanonymous.org/meeting-search-f2f/', 'why': 'Not reached (round 3 time box).'},
  {'name': 'ITAA', 'url': 'https://internetaddictsanonymous.org/', 'why': 'Its meetings page sits behind a "confirm you are human" wall and its old /meetings/ address is gone; not worked around.'},
  {'name': 'Emotions Anonymous', 'url': 'https://emotionsanonymous.org/find-an-ea-meeting/', 'why': 'Not reached (round 3 time box).'},
]
TAGMAP_TSML = {'O': 'open', 'C': 'closed', 'BE': 'beginners', 'SP': 'speaker', 'ST': 'step', 'W': 'women', 'M': 'men',
               'Y': 'young', 'LGBTQ': 'lgbtq', 'G': 'lgbtq', 'L': 'lgbtq', 'T': 'lgbtq', 'S': 'spanish', 'X': 'wheelchair', 'MED': 'meditation', 'LIT': 'literature',
               'B': 'literature', 'BB': 'literature', 'A': 'secular', 'AG': 'secular', 'ASL': 'asl', 'NEW': 'beginners', 'D': 'discussion'}
TAGMAP_BMLT = {'O': 'open', 'C': 'closed', 'BEG': 'beginners', 'NEW': 'beginners', 'SPK': 'speaker', 'SD': 'speaker', 'STP': 'step', 'W': 'women', 'M': 'men',
               'Y': 'young', 'GL': 'lgbtq', 'LGBTQ+': 'lgbtq', 'ESP': 'spanish', 'BL': 'spanish', 'WC': 'wheelchair', 'ME': 'meditation', 'BT': 'literature',
               'LIT': 'literature', 'JFT': 'literature', 'LC': 'literature', 'IW': 'literature', 'Ag': 'secular', 'A': 'secular', 'ASL': 'asl', 'D': 'discussion'}

def hhmm(s):
    m = re.match(r'(\d{1,2}):(\d{2})', s or '')
    return f'{int(m.group(1)):02d}:{m.group(2)}' if m else None

def city_zip(addr):
    m = re.search(r',\s*([^,]+),\s*FL\s*(\d{5})?', addr or '')
    return (m.group(1).strip(), m.group(2)) if m else ('', None)

def na_meetings():
    src = MEETING_SOURCES['na_sfl']
    data = get_json('https://bmlt.sezf.org/main_server/client_interface/json/', params={'switcher': 'GetSearchResults', 'services[]': ['20', '134'], 'recursive': '1'}, timeout=90)
    out = []
    for m in data:
        if m.get('published') not in ('1', 1): continue
        fmts = [f.strip() for f in (m.get('formats') or '').split(',') if f.strip()]
        vt = str(m.get('venue_type') or '1')
        att = {'1': 'in', '2': 'online', '3': 'hybrid'}.get(vt, 'in')
        if 'TC' in fmts and att == 'in': continue          # temporarily closed facility
        if 'ASM' in fmts or re.search(r'(?i)subcommittee|service (committee|meeting)|\bASC\b|\bRSC\b|business meeting', m.get('meeting_name') or ''): continue   # NA service/committee meetings, not recovery meetings
        tags = sorted({TAGMAP_BMLT[f] for f in fmts if f in TAGMAP_BMLT})
        if m.get('lang_enum') == 'es' or m.get('service_body_bigint') == '39': tags = sorted(set(tags) | {'spanish'})
        try: lat, lng = round(float(m['latitude']), 5), round(float(m['longitude']), 5)
        except Exception: lat = lng = None
        if att == 'online': lat = lng = None
        day = int(m['weekday_tinyint']) - 1        # BMLT 1=Sunday -> 0=Sunday
        t = hhmm(m.get('start_time'))
        dur = hhmm(m.get('duration_time')) or '01:00'
        h, mi = map(int, t.split(':')); dh, dm = map(int, dur.split(':'))
        end_min = (h * 60 + mi + dh * 60 + dm) % 1440
        street = clean(m.get('location_street')); city = clean(m.get('location_municipality'))
        addr = ', '.join(x for x in [street, city, 'FL ' + clean(m.get('location_postal_code_1'))] if x.strip() and x != 'FL ')
        out.append({'id': 'na' + m['id_bigint'], 'prog': 'NA', 'name': clean(m.get('meeting_name'), 80), 'day': day, 'time': t,
                    'end': f'{end_min // 60:02d}:{end_min % 60:02d}', 'att': att, 'loc': clean(m.get('location_text'), 80),
                    'addr': addr if att != 'online' else '', 'city': city, 'zip': clean(m.get('location_postal_code_1')) or None,
                    'lat': lat, 'lng': lng, 'tags': tags, 'join': clean(m.get('virtual_meeting_link')) or None,
                    'phone': clean(m.get('phone_meeting_number')) or None,
                    'notes': clean(' '.join(x for x in [m.get('location_info'), m.get('comments'), m.get('virtual_meeting_additional_info')] if x), 200) or None,
                    'area': clean(m.get('service_body_name')),
                    'url': 'https://bmlt.sezf.org/main_server/client_interface/json/?switcher=GetSearchResults&meeting_key=id_bigint&meeting_key_value=' + m['id_bigint'],
                    'src': 'na_sfl'})
    return out

def tsml_meetings(key):
    src = MEETING_SOURCES[key]
    data = get_json(src['feed'], timeout=90)
    out = []
    for m in data:
        att = {'in_person': 'in', 'online': 'online', 'hybrid': 'hybrid'}.get(m.get('attendance_option') or 'in_person')
        if not att or m.get('day') in (None, '') or not m.get('time'): continue
        types = m.get('types') or []
        if 'TC' in types and att == 'in': continue
        if 'BUS' in types and len(types) <= 2 or re.search(r'(?i)\bintergroup\b.*\bmeeting\b|business meeting|subcommittee', m.get('name') or ''): continue
        tags = sorted({TAGMAP_TSML[t] for t in types if t in TAGMAP_TSML})
        addr = clean(m.get('formatted_address')).replace(', USA', '')
        city, z = city_zip(addr)
        if not city: city = clean((m.get('regions') or [m.get('region') or ''])[-1])
        try: lat, lng = round(float(m['latitude']), 5), round(float(m['longitude']), 5)
        except Exception: lat = lng = None
        if att == 'online' or m.get('approximate') == 'yes': lat = lng = (None if att == 'online' else lat), (None if att == 'online' else lng)
        if isinstance(lat, tuple): lat, lng = lat
        out.append({'id': key + '-' + str(m.get('id') or m.get('slug')), 'prog': 'AA', 'name': clean(m.get('name'), 80), 'day': int(m['day']),
                    'time': hhmm(m['time']), 'end': hhmm(m.get('end_time')), 'att': att, 'loc': clean(m.get('location'), 80) if att != 'online' else '',
                    'addr': addr if att != 'online' else '', 'city': city, 'zip': z, 'lat': lat, 'lng': lng, 'tags': tags,
                    'join': clean(m.get('conference_url')) or None, 'phone': clean(m.get('conference_phone')) or None,
                    'notes': clean(' '.join(x for x in [m.get('notes'), m.get('location_notes'), m.get('conference_url_notes')] if x), 200) or None,
                    'area': clean(m.get('region')), 'url': m.get('url'), 'src': key})
    return out

def oiaa_meetings():
    data = get_json(MEETING_SOURCES['aa_online']['feed'], timeout=120)
    out = []
    for m in data:
        types = m.get('types') or []
        lang = 'es' if ('S' in types or 'ES' in types) else ('en' if 'EN' in types else None)
        if not lang or m.get('day') in (None, '') or not m.get('time'): continue
        if not (m.get('conference_url') or m.get('conference_phone')): continue
        tags = sorted({TAGMAP_TSML[t] for t in types if t in TAGMAP_TSML} | ({'spanish'} if lang == 'es' else set()))
        out.append({'id': 'oiaa-' + (m.get('slug') or hashlib.md5(json.dumps(m).encode()).hexdigest()[:10]), 'prog': 'AA', 'name': clean(m.get('name'), 80),
                    'day': int(m['day']), 'time': hhmm(m['time']), 'end': hhmm(m.get('end_time')), 'tz': m.get('timezone') or 'UTC', 'att': 'online',
                    'tags': tags, 'join': clean(m.get('conference_url')) or None, 'phone': clean(m.get('conference_phone')) or None,
                    'url': m.get('url'), 'src': 'aa_online'})
    return out

# ---------- all fellowships: source framework (round 2) ----------
# Program codes -> display names (EN, ES). Lock screen and notifications never show any of these (see hub.js reminder preview).
PROGRAMS = {
  'AA': ('AA', 'AA'), 'NA': ('NA', 'NA'), 'Al-Anon': ('Al-Anon', 'Al-Anon'), 'Alateen': ('Alateen', 'Alateen'), 'Nar-Anon': ('Nar-Anon', 'Nar-Anon'),
  'ACA': ('ACA (Adult Children)', 'ACA (Hijos Adultos)'), 'CoDA': ('CoDA', 'CoDA'), 'SA': ('SA', 'SA'), 'SAA': ('SAA', 'SAA'), 'SLAA': ('SLAA', 'SLAA'),
  'SCA': ('SCA', 'SCA'), 'OA': ('OA', 'OA'), 'GA': ('GA', 'GA'), 'Gam-Anon': ('Gam-Anon', 'Gam-Anon'), 'RD': ('Recovery Dharma', 'Recovery Dharma'),
  'Refuge': ('Refuge Recovery', 'Refuge Recovery'), 'SMART': ('SMART Recovery', 'SMART Recovery'), 'CR': ('Celebrate Recovery', 'Celebrate Recovery'),
  'CA': ('CA', 'CA'), 'CMA': ('CMA', 'CMA'), 'MA': ('MA', 'MA'), 'HA': ('HA', 'HA'), 'DA': ('DA', 'DA'), 'ITAA': ('ITAA', 'ITAA'), 'EA': ('EA', 'EA'),
  'Other': ('Other', 'Otro'),
}
PROG_ALIASES = {'ALANON': 'Al-Anon', 'AL-ANON': 'Al-Anon', 'ALATEEN': 'Alateen', 'NARANON': 'Nar-Anon', 'CODA': 'CoDA', 'RECOVERY DHARMA': 'RD',
                'SMART RECOVERY': 'SMART', 'CELEBRATE RECOVERY': 'CR', 'GAMANON': 'Gam-Anon', 'REFUGE RECOVERY': 'Refuge'}
def norm_prog(p):
    if not p: return 'Other'
    if p in PROGRAMS: return p
    u = str(p).strip().upper()
    for k in PROGRAMS:
        if k.upper() == u: return k
    return PROG_ALIASES.get(u.replace('_', ' '), 'Other')

SOFLO_BOX = (25.10, 26.98, -80.95, -79.95)       # Miami-Dade, Broward, Palm Beach (lat min/max, lng min/max)
def in_soflo(m):
    if m.get('lat') is not None and m.get('lng') is not None:
        return SOFLO_BOX[0] <= m['lat'] <= SOFLO_BOX[1] and SOFLO_BOX[2] <= m['lng'] <= SOFLO_BOX[3]
    z = str(m.get('zip') or '')[:5]
    if not z:
        mm = re.search(r'\bFL\s*(33[0-4]\d\d)\b', m.get('addr') or ''); z = mm.group(1) if mm else ''
    return z[:3] in ('330', '331', '332', '333', '334') and not (z == '33001' or '33036' <= z <= '33070')   # 33001/33036-33070 = the Keys

def core_sources():
    out = []
    for k, fn in (('na_sfl', na_meetings), ('aa_pbc', lambda: tsml_meetings('aa_pbc')), ('aa_spbc', lambda: tsml_meetings('aa_spbc')), ('aa_online', oiaa_meetings)):
        s = dict(MEETING_SOURCES[k]); s.update(key=k, ttl_days=1, scope='online' if k == 'aa_online' else 'local', venue=None, fn=fn, module='core')
        out.append(s)
    return out

def module_sources():
    """Every hub/sources/<group>.py exposing SOURCES + fetch(key) (see sources/CONTRACT.md)."""
    import importlib, pkgutil
    sys.path.insert(0, HERE)
    out, broken = [], []
    for mi in pkgutil.iter_modules([os.path.join(HERE, 'sources')]):
        if mi.name.startswith('_'): continue
        try:
            mod = importlib.import_module('sources.' + mi.name)
            for s in getattr(mod, 'SOURCES', []):
                s = dict(s); key = s['key']
                s.update(fn=(lambda k=key, m=mod: m.fetch(k)), module=mi.name)
                s.setdefault('ttl_days', 1); s.setdefault('scope', 'local'); s.setdefault('venue', None)
                out.append(s)
        except Exception as e:
            broken.append({'module': mi.name, 'error': repr(e)[:200]}); log(f'[module {mi.name}] import FAILED: {e!r}')
    return out, broken

def cache_path(key): return os.path.join(RAW, f'last_{key}.json')
def read_cache(key):
    p = cache_path(key)
    if not os.path.exists(p): return None
    try: return json.load(open(p))
    except Exception: return None
def age_days(iso):
    try: return (NOW - dt.datetime.strptime(iso, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=dt.timezone.utc)).total_seconds() / 86400
    except Exception: return 1e9

def fetch_source(s):
    t0 = time.time(); key = s['key']
    rows = s['fn']()
    min_rows = 10 if s['module'] == 'core' else 1
    if len(rows) < min_rows: raise RuntimeError(f'only {len(rows)} rows')
    for r in rows:
        r.setdefault('src', key); r['prog'] = norm_prog(r.get('prog') or s.get('program'))
        if s.get('venue') and not r.get('venue'): r['venue'] = s['venue']['key']
    json.dump({'fetched_at': STAMP, 'rows': rows}, open(cache_path(key), 'w'))
    log(f'[{key}] ok {len(rows)} in {time.time()-t0:.1f}s')
    return rows

def run_sources(srcs, budget):
    """Daily run: ttl_days 1 sources are fetched; slower (weekly) sources come from their cache while it is younger than
    their ttl. A stale weekly cache is refreshed by a detached `--slow` run, so the daily build never waits on a browser."""
    from concurrent.futures import ThreadPoolExecutor, wait
    res, todo, stale_slow = {}, [], []
    for s in srcs:
        if s.get('venue_only'): res[s['key']] = ([], None, None, 'venue only'); continue
        c = read_cache(s['key'])
        if s['ttl_days'] > 1 and c and age_days(c['fetched_at']) < s['ttl_days']:
            res[s['key']] = (c['rows'], c['fetched_at'], None, 'cache')
        elif s['ttl_days'] > 1 and c:
            res[s['key']] = (c['rows'], c['fetched_at'], None, 'cache (refresh queued)'); stale_slow.append(s['key'])
        else:
            todo.append(s)
    ex = ThreadPoolExecutor(16)
    futs = {ex.submit(fetch_source, s): s for s in todo}
    done, notdone = wait(futs, timeout=budget)
    for f, s in futs.items():
        c = read_cache(s['key'])
        if f in done and f.exception() is None:
            res[s['key']] = (f.result(), STAMP, None, 'fetched')
        else:
            e = f.exception() if f in done else TimeoutError(f'not done in {budget}s')
            log(f"[{s['key']}] FAILED: {e!r}")
            res[s['key']] = (c['rows'], c['fetched_at'], repr(e)[:200], 'cache after failure') if c else ([], None, repr(e)[:200], 'failed')
    ex.shutdown(wait=False, cancel_futures=True)
    if stale_slow and '--no-slow' not in sys.argv:
        import subprocess
        subprocess.Popen([sys.executable, os.path.abspath(__file__), '--slow', ','.join(stale_slow)], cwd=HERE, start_new_session=True,
                         stdout=open(os.path.join(HERE, 'slow_refresh.log'), 'a'), stderr=subprocess.STDOUT)
        log(f'[slow] queued a detached refresh of {len(stale_slow)} weekly sources: {",".join(stale_slow)}')
    return res

def slow_refresh(keys):
    srcs = {s['key']: s for s in core_sources() + module_sources()[0]}
    for k in keys:
        if k in srcs:
            try: fetch_source(srcs[k])
            except Exception as e: log(f'[{k}] slow refresh FAILED: {e!r}')
    print('\n'.join(LOG))

def geo_dist(a, b, c, d):
    import math
    R = 3958.8; r = math.radians; dl = r(c - a); dn = r(d - b)
    h = math.sin(dl / 2) ** 2 + math.cos(r(a)) * math.cos(r(c)) * math.sin(dn / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))
def street_key(addr):
    m = re.match(r'\s*(\d+)\s+([NSEW]{1,2}\s+)?(\w+)', (addr or '').upper())
    return (m.group(1), m.group(3)) if m else None

def build_meetings():
    srcs = core_sources()
    mods, broken = module_sources()
    srcs += mods
    budget = float(os.environ.get('HUB_SOURCE_BUDGET', '75'))
    res = run_sources(srcs, budget)
    zips = json.load(open(os.path.join(OUT, 'zips-fl.json')))['zips'] if os.path.exists(os.path.join(OUT, 'zips-fl.json')) else {}
    venues = {}
    for s in srcs:
        if s.get('venue'): venues[s['venue']['key']] = dict(s['venue'], source=s['key'], page=s.get('page'))
    local, online, sources = [], [], []
    for s in srcs:
        rows, fetched, err, how = res[s['key']]
        nl = no = dropped = 0
        for m in rows:
            m = dict(m); m['src'] = s['key']; m['prog'] = norm_prog(m.get('prog') or s.get('program'))
            if not m.get('day') in range(7) or not hhmm(m.get('time')): dropped += 1; continue
            m['time'] = hhmm(m['time'])
            if m.get('end'): m['end'] = hhmm(m['end'])
            is_online = m.get('att') == 'online'
            if s['scope'] == 'online' or (s['scope'] == 'both' and is_online and not in_soflo(m)):
                m['att'] = 'online'; online.append(m); no += 1; continue
            if m.get('lat') is None and m.get('zip') and str(m['zip'])[:5] in zips and not is_online:
                m['lat'], m['lng'] = zips[str(m['zip'])[:5]]; m['approx'] = 1        # ZIP centroid: good enough for "within N miles"
            if not is_online and not in_soflo(m): dropped += 1; continue
            local.append(m); nl += 1
        sources.append({'key': s['key'], 'name': s['name'], 'program': norm_prog(s.get('program')) if s.get('program') != 'Mixed' else 'Mixed',
                        'page': s.get('page'), 'feed': s.get('feed'), 'fetched_at': fetched, 'count': nl + no, 'local': nl, 'online': no,
                        'error': err, 'how': how, 'ttl_days': s['ttl_days'], 'venue': (s.get('venue') or {}).get('key'), 'module': s['module']})
    # tag feed meetings held at a known clubhouse (same building), then drop clubhouse-schedule duplicates of feed meetings
    vlist = [v for v in venues.values() if v.get('lat') is not None]
    vkeys = {street_key(v.get('addr')): k for k, v in venues.items() if street_key(v.get('addr'))}
    for m in local:
        if m.get('venue') or m.get('att') == 'online': continue
        sk = street_key(m.get('addr'))
        if sk and sk in vkeys: m['venue'] = vkeys[sk]; continue
        if m.get('lat') is not None and not m.get('approx'):
            for v in vlist:
                if geo_dist(m['lat'], m['lng'], v['lat'], v['lng']) < 0.06: m['venue'] = v['key']; break
    seen, uniq = {}, []
    # feeds first so a fellowship's own listing wins over the clubhouse's copy of it
    for m in sorted(local, key=lambda m: 1 if (m['src'] in venues and False) or any(v['source'] == m['src'] for v in venues.values()) else 0):
        k1 = (m['prog'], m['name'].lower(), m['day'], m['time'], (m.get('addr') or '').lower()[:30], m.get('join') if m['att'] == 'online' else '')
        k2 = (m['prog'], m.get('venue'), m['day'], m['time']) if m.get('venue') else None
        if k1 in seen or (k2 and k2 in seen): continue
        seen[k1] = 1
        if k2: seen[k2] = 1
        uniq.append(m)
    local = uniq
    seen, uo = set(), []
    for m in online:
        k = (m['prog'], m['name'].lower(), m['day'], m['time'], m.get('join') or m.get('url'))
        if k in seen: continue
        seen.add(k); uo.append(m)
    online = uo
    for m in local + online:
        for k in [k for k, v in m.items() if v in (None, '', [])]: del m[k]
        if m.get('lat') is not None: m['lat'], m['lng'] = round(m['lat'], 5), round(m['lng'], 5)
    # venue meeting counts (only venues that actually have meetings in the list)
    vcount = {}
    for m in local:
        if m.get('venue'): vcount[m['venue']] = vcount.get(m['venue'], 0) + 1
    venues_out = [dict(v, count=vcount[k]) for k, v in venues.items() if vcount.get(k)]
    progs = {}
    for m in local: progs.setdefault(m['prog'], [0, 0])[0] += 1
    for m in online: progs.setdefault(m['prog'], [0, 0])[1] += 1
    programs = [{'code': p, 'en': PROGRAMS.get(p, (p, p))[0], 'es': PROGRAMS.get(p, (p, p))[1], 'local': c[0], 'online': c[1]}
                for p, c in sorted(progs.items(), key=lambda x: (x[0] == 'Other', -(x[1][0] + x[1][1])))]
    meta = {'generated_at': STAMP, 'sources': sources, 'not_included': NOT_INCLUDED + [{'name': b['module'], 'url': '', 'why': 'module failed to load: ' + b['error']} for b in broken],
            'programs': programs, 'venues': venues_out,
            'counts': {'local': len(local), 'online_worldwide': len(online), 'by_program_local': {p['code']: p['local'] for p in programs},
                       'by_program_online': {p['code']: p['online'] for p in programs}, 'by_venue': vcount}}
    # online: one compact file per program, loaded only when "Online" is picked (AA alone is ~7k rows)
    for f in os.listdir(OUT):
        if f.startswith('meetings-online'): os.remove(os.path.join(OUT, f))
    tzs = sorted({m.get('tz') or 'America/New_York' for m in online}); srcs_on = sorted({m['src'] for m in online})
    online_files = {}
    for p in sorted({m['prog'] for m in online}):
        rows = [[m['id'], m['name'], m['day'], m['time'], tzs.index(m.get('tz') or 'America/New_York'), m.get('join', ''), ','.join(m.get('tags', [])),
                 m.get('url', ''), srcs_on.index(m['src']), m.get('phone', '')] for m in online if m['prog'] == p]
        fn = 'meetings-online-' + re.sub(r'[^a-z0-9]+', '-', p.lower()) + '.json'
        json.dump({'generated_at': STAMP, 'prog': p, 'tz': tzs, 'srcs': srcs_on, 'cols': ['id', 'name', 'day', 'time', 'tz', 'join', 'tags', 'url', 'src', 'phone'], 'rows': rows},
                  open(os.path.join(OUT, fn), 'w'), separators=(',', ':'), ensure_ascii=False)
        online_files[p] = fn
    meta['online_files'] = online_files
    json.dump({**meta, 'meetings': local}, open(os.path.join(OUT, 'meetings.json'), 'w'), separators=(',', ':'), ensure_ascii=False)
    return meta

# ---------- ZIP centroids (US Census 2023 ZCTA gazetteer, Florida) ----------
def build_zips():
    p = os.path.join(OUT, 'zips-fl.json')
    if os.path.exists(p): return
    src = os.path.join(RAW, '2023_Gaz_zcta_national.txt')
    z = {}
    for line in open(src):
        f = line.split('\t')
        if f[0].isdigit() and 32000 <= int(f[0]) <= 34999:
            z[f[0]] = [round(float(f[5]), 4), round(float(f[6]), 4)]
    json.dump({'source': 'US Census Bureau 2023 ZCTA Gazetteer (https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2023_Gazetteer/)', 'zips': z},
              open(p, 'w'), separators=(',', ':'))

# ---------- sober-friendly events ----------
SOBER = re.compile(r"(?i)\b(sober(?:[- ]curious|ly| social| meetups?| events?| community| living)?|sobriety|alcohol[- ]free|substance[- ]free|drug[- ]free|"
                   r"zero[- ]proof|non[- ]alcoholic|mocktails?|dry (?:january|july)|in recovery|recovery (?:community|month|rally|walk|run|5k|festival|celebration|"
                   r"yoga|meditation|meeting|support|speakers?|open mic|book club|fellowship)|addiction recovery|celebrate recovery|smart recovery|12[- ]step|"
                   r"twelve[- ]step|alcoholics anonymous|narcotics anonymous|al-anon)\b")
ALCOHOL = re.compile(r"(?i)\b(beer|beers|brew(?:ery|eries|ing|pub|fest)?|taproom|wine|wines|winery|vino|cocktails?|happy hour|bar crawl|pub crawl|open bar|"
                     r"spirits|distiller(?:y|ies)|tasting|tastings|sake|sangria|margaritas?|mimosas?|bottomless|tequila|mezcal|rum|vodka|whiske?y|bourbon|"
                     r"champagne|prosecco|bubbly|bubbles|martinis?|beverages|booze|boozy|drinks?|drinking|21\+|21 and over|21 & over|nightclub|club night|lounge|saloon|tavern|pub|bar|"
                     r"oktoberfest|after[- ]party|rave|bottle service|hookah|cannabis|cbd|kava|psychedelic|ayahuasca|mushroom)\b")
ACTIVITY = re.compile(r"(?i)\b(yoga|meditation|meditate|mindful(?:ness)?|breathwork|sound bath|tai chi|qigong|run club|running club|fun run|5k|10k|"
                      r"walk(?:ing)? club|nature walk|guided walk|bird ?walk|hike|hiking|beach clean[- ]?up|park clean[- ]?up|kayak|paddle(?:board)?|"
                      r"sunrise|bike ride|group ride|cycling club|volunteer|pickleball|stretch|pilates|zumba|dance fitness)\b")
POSITIVE_CAT = {'Sports & Fitness', 'Outdoors & Nature', 'Community', 'Arts & Culture'}

def load_soflo():
    cache_file = os.path.join(RAW, 'last_soflo_events.js')
    t = None
    for url in SOFLO_URLS:
        try:
            r = requests.get(url, headers=UA, timeout=30)
            r.raise_for_status()
            txt = r.content.decode('utf-8', 'replace')
            if '{' in txt and '}' in txt:
                t = txt
                try:
                    open(cache_file, 'w', encoding='utf-8').write(t)
                except Exception:
                    pass
                log(f'[soflo] fetched {len(t)} bytes from {url}')
                break
        except Exception as ex:
            log(f'[soflo] fetch failed {url}: {ex!r}')
    if t is None and os.path.exists(cache_file):
        t = open(cache_file, encoding='utf-8').read()
        log('[soflo] using cached last_soflo_events.js')
    if t is None:
        log('[soflo] no events.js available, returning empty list')
        return None, []
    D = json.loads(t[t.index('{'):t.rindex('}') + 1])
    rows = []
    for k in ('curated', 'feed', 'library'):
        for e in D.get(k) or []: rows.append((k, e))
    return D.get('updated'), rows

def eventbrite_sober():
    """Eventbrite's 'sober events' discovery pages for South Florida cities. v3.6.3: read from the events_national.py cache
    (discovery-page JSON-LD + each event's own page, fetched detached), because Eventbrite's /api/v3/destination/events/,
    which this used before, is Disallowed in eventbrite.com/robots.txt."""
    import events_national as EN
    try: res = json.load(open(EN.CACHE)); pages = json.load(open(EN.PAGES))
    except Exception: log('[eventbrite-sober] no national cache yet'); return []
    out = []
    for r in res.get('rows') or []:
        if r.get('src') != 'eventbrite' or r.get('metro') != 'mia': continue
        pg = pages.get(r['url']) or {}
        a, b2 = EN.eb_time(pg.get('startDate') or ''), EN.eb_time(pg.get('endDate') or '')
        try: sd = a.date() if a else dt.date.fromisoformat((r.get('sd') or '')[:10]); ed = (b2.date() if b2 else None) or sd
        except Exception: continue
        if (ed - sd).days > 5: continue
        dates = [(sd + dt.timedelta(days=i)).isoformat() for i in range((ed - sd).days + 1)] if (ed - sd).days > 1 else [sd.isoformat()]
        free = pg.get('price_hi') == 0 if 'price_hi' in pg else False
        out.append({'title': r.get('title'), 'dates': dates, 'start': a.strftime('%H:%M') if a and 'T' in pg.get('startDate', '') else None,
                    'end': b2.strftime('%H:%M') if b2 and 'T' in pg.get('endDate', '') else None, 'venue': r.get('venue'), 'address': r.get('address'),
                    'city': r.get('city'), 'zip': r.get('zip'), 'lat': r.get('lat'), 'lng': r.get('lng'), 'free': free,
                    'price_text': 'Free' if free else None, 'desc': r.get('desc'), 'url': r.get('url'), 'source': 'Eventbrite'})
    log(f'[eventbrite-sober] {len(out)} South Florida rows from the national cache')
    return out

def classify(e):
    title = e.get('title') or ''; desc = e.get('desc') or ''; venue = e.get('venue') or ''
    blob = f'{title} {desc}'
    if SOBER.search(blob):
        if ALCOHOL.search(f'{title} {venue}') and not re.search(r'(?i)alcohol[- ]free|zero[- ]proof|non[- ]alcoholic|sober|mocktail|recovery', title):
            return None, 'sober word but alcohol in title/venue'
        if re.search(r'(?i)\b(disaster|injury|muscle|data|economic|storm|hurricane|post[- ]surgery|wound)\b recovery|recovery (?:drink|boots|session)', blob):
            return None, 'non-addiction recovery'
        hits = {h.group(0).lower() for h in SOBER.finditer(blob)}
        if hits <= {'mocktail', 'mocktails'} and not re.search(r'(?i)mocktail', title):
            return None, 'only mentions mocktails (alcohol likely served too)'
        return 'recovery', SOBER.search(blob).group(0)
    if ACTIVITY.search(title) and not ALCOHOL.search(f'{title} {desc} {venue}') and not re.search(r'(?i)\b(party|parties|festival|fest|gala|night out|after ?party|concert)\b', f'{title} {desc}'):
        st = e.get('start') or ''
        if st and int(st[:2]) >= 19: return None, 'evening'
        if e.get('tags') and '21+' in e['tags']: return None, '21+'
        return 'activity', ACTIVITY.search(title).group(0)
    return None, None

def build_events():
    """Events -> site/hub/data/events.json (public: verified sober events + healthy activities) and events-review.json (admin queue:
    everything, incl. unconfirmed sober-looking listings, social-media items and host submissions). See events_verify.py for the rules."""
    import events_verify as V
    t0 = time.time()
    updated, rows = load_soflo()
    try: rows += [('eventbrite-sober', e) for e in eventbrite_sober()]; eb_err = None
    except Exception as ex: eb_err = repr(ex)[:200]; log('[eventbrite-sober] FAILED', eb_err)
    today = dt.date.today().isoformat(); horizon = (dt.date.today() + dt.timedelta(days=45)).isoformat()
    cand, why_no, byid = [], {}, {}
    for kind, e in rows:
        dates = [d for d in (e.get('dates') or []) if today <= d <= horizon]
        if not dates: continue
        tier, why = classify(e)
        if not tier:
            if why: why_no[why] = why_no.get(why, 0) + 1
            continue
        sid = V.stable_id(e)
        if sid in byid:                                   # same title + venue + start time = one series: merge its dates
            o = byid[sid]; o['dates'] = sorted(set(o['dates']) | set(dates))[:8]; continue
        ev = {'id': sid, 'tier': tier, 'match': why, 'origin': 'web',
              'title': clean(e.get('title'), 110), 'dates': dates[:8], 'start': e.get('start'), 'end': e.get('end'),
              'venue': clean(e.get('venue'), 80), 'address': clean(e.get('address'), 120), 'city': e.get('city'), 'zip': e.get('zip'),
              'county': V.county_of(e), 'lat': e.get('lat'), 'lng': e.get('lng'), 'free': bool(e.get('free')), 'price': e.get('price_text'),
              'desc': clean(e.get('desc'), 260), 'url': e.get('url'), 'source': e.get('source') or kind, 'via': kind}
        byid[sid] = ev; cand.append(ev)
    cache, ev_stats = V.gather_evidence(cand, budget=float(os.environ.get('HUB_EVIDENCE_BUDGET', 25)))
    for ev in cand: ev['verify'] = V.auto_verify(ev, ev['tier'], cache)
    social, social_meta = V.load_social(today, horizon)
    webkeys = {(re.sub(r'\W+', '', (e.get('title') or '').lower())[:40], d) for e in cand for d in e['dates']}
    social = [e for e in social if (re.sub(r'\W+', '', (e.get('title') or '').lower())[:40], e['dates'][0]) not in webkeys]   # already listed from the web
    for e in social: e['county'] = e.get('county') or V.county_of(e); e['tier'] = 'social'
    decisions, extra, dec_err = V.load_decisions()
    allv = cand + social
    for x in extra:                                       # admin-verified submissions / social items (snapshots from D1)
        if x.get('id') and x['id'] not in {e['id'] for e in allv} and any(today <= d <= horizon for d in x.get('dates') or []):
            x = dict(x, dates=[d for d in x['dates'] if today <= d <= horizon]); x['tier'] = x.get('tier') or x.get('origin') or 'submitted'; allv.append(x)
    for ev in allv: V.apply_decision(ev, decisions.get(ev['id']))
    for ev in allv:
        st = ev['verify']['status']
        ev['section'] = 'sober' if st == 'verified' else 'hidden' if st == 'rejected' else 'healthy' if ev['tier'] == 'activity' else 'queue'
    allv.sort(key=lambda x: (x['dates'][0], x.get('start') or ''))
    for m in allv:
        for k in [k for k, v in m.items() if v in (None, '', [])]: del m[k]
    pub = [e for e in allv if e['section'] in ('sober', 'healthy')]
    counts = {'verified': sum(e['verify']['status'] == 'verified' for e in allv), 'listed': sum(e['verify']['status'] == 'listed' for e in allv),
              'rejected': sum(e['verify']['status'] == 'rejected' for e in allv), 'social': len(social),
              'sober_section': sum(e['section'] == 'sober' for e in allv), 'healthy_section': sum(e['section'] == 'healthy' for e in allv),
              'review_queue': sum(e['section'] in ('queue', 'healthy') for e in allv),
              'verified_by_rule': {r: sum(e['verify'].get('rule') == r and e['verify']['status'] == 'verified' for e in allv) for r in ('host_page_says_sober', 'recovery_org', 'confirmed_by_admin')},
              'excluded_reasons': why_no}
    meta = {'generated_at': STAMP, 'soflo_updated': updated, 'eventbrite_sober_error': eb_err, 'decisions_error': dec_err,
            'evidence': ev_stats, 'social': social_meta, 'seconds': round(time.time() - t0, 1),
            'rules': {'verified': 'Sober events: the event\'s own page (the host\'s listing) explicitly says sober, alcohol-free or recovery, or a recovery fellowship, recovery org or clubhouse runs or hosts it, or an admin confirmed it. The quote and page are stored per event.',
                      'listed': 'Pulled automatically, not confirmed with the host.',
                      'healthy': 'Healthy activities: daytime yoga, runs, hikes, meditation and similar whose listing mentions no alcohol. Not sober events; shown separately.',
                      'social': 'Social-media items are never verified automatically; they wait in the admin review queue.'},
            'counts': counts}
    json.dump({**meta, 'events': pub}, open(os.path.join(OUT, 'events.json'), 'w'), separators=(',', ':'), ensure_ascii=False)
    json.dump({**meta, 'events': allv}, open(os.path.join(RAW, 'events-review.json'), 'w'), separators=(',', ':'), ensure_ascii=False)
    log(f"[events] verified {counts['verified']} listed {counts['listed']} social {counts['social']} in {meta['seconds']}s")
    return meta

if __name__ == '__main__':
    if '--slow' in sys.argv:
        slow_refresh(sys.argv[sys.argv.index('--slow') + 1].split(',')); os._exit(0)
    what = [a for a in sys.argv[1:] if not a.startswith('--')] or ['meetings', 'events', 'zips']
    res = {'started': STAMP}
    if 'zips' in what: build_zips()
    if 'meetings' in what: res['meetings'] = build_meetings()
    if 'events' in what: res['events'] = build_events()
    res['log'] = LOG; res['finished'] = dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    json.dump(res, open(os.path.join(HERE, 'last_build.json'), 'w'), indent=1)
    errs = [s for s in (res.get('meetings') or {}).get('sources', []) if s['error']]
    print(json.dumps({'ok': True, 'meeting_counts': (res.get('meetings') or {}).get('counts'), 'event_counts': (res.get('events') or {}).get('counts'), 'source_errors': errs}))
    sys.stdout.flush(); os._exit(0)      # never wait on a source thread that overran its budget
