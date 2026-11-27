#!/usr/bin/env python3
"""Still Present Hub: sober events beyond South Florida (3.6.3). Ten biggest US metros + Miami, published per state.

  python3 events_national.py fetch   detached (refresh.sh): exits at once while raw/events_national.json is younger than
                                     FETCH_TTL_H (20 h). Reads the public sources below, then each Eventbrite candidate's own
                                     event page (cached 7 days in raw/events_national_pages.json). ~1-3 min, never blocks the daily run.
  python3 events_national.py build   daily, a few seconds: cache + South Florida events.json -> events-index.json, events-<st>.json,
                                     and appends the national rows to events-review.json (admin queue).

Sources (all public, plain GET, robots.txt checked 2026-11-03):
  - The Phoenix (thephoenix.org/explore-events, server-rendered page, locationFilter query; robots allows it). A sober
    community: "All we ask is that anyone who participates in Phoenix-led activities has been substance free for at least 48
    hours." (thephoenix.org/our-ethos, re-read at each fetch). Verified, rule recovery_org. Its recovery *meetings* are skipped
    here (they are meetings, not events).
  - AA intergroup calendars that publish The Events Calendar's public REST feed (/wp-json/tribe/events/v1/events): Dallas,
    Washington DC, Southeastern PA (Philadelphia), Atlanta. Run/listed by an AA intergroup -> verified, rule recovery_org.
    Service committee / business meetings are dropped.
  - Eventbrite discovery pages /d/<city>/{sober-events,recovery,alcohol-free}/ (JSON-LD ItemList) and each candidate's own /e/ page
    (JSON-LD: time + the host's words). Eventbrite's /api/v3/destination/events/ is Disallowed in robots.txt and is NOT used.
    Same rules as South Florida: verified only when the host's page says sober / recovery or a recovery org runs it; healthy
    activities -> "healthy" (listed); other sober-looking listings -> review queue (listed).
"""
import sys, os, re, json, time, datetime as dt, html as H, urllib.request, urllib.parse, concurrent.futures as cf
from zoneinfo import ZoneInfo
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import events_verify as V
OUT = os.environ.get('HUB_OUT_DIR') or os.path.join(os.path.dirname(HERE), 'hub', 'data')
RAW = os.path.join(HERE, 'raw')
CACHE = os.path.join(RAW, 'events_national.json')
PAGES = os.path.join(RAW, 'events_national_pages.json')
FETCH_TTL_H = 20
UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36 (Still Present Hub events cache; contact stillpresent.pages.dev)'
HORIZON_DAYS = 45

METROS = [  # key, label, state, lat, lng, tz, eventbrite slugs, intergroup tribe feeds
  ('nyc', 'New York', 'NY', 40.7128, -74.0060, 'America/New_York', ['ny--new-york'], []),
  ('la', 'Los Angeles', 'CA', 34.0522, -118.2437, 'America/Los_Angeles', ['ca--los-angeles'], []),
  ('chi', 'Chicago', 'IL', 41.8781, -87.6298, 'America/Chicago', ['il--chicago'], []),
  ('dfw', 'Dallas', 'TX', 32.7767, -96.7970, 'America/Chicago', ['tx--dallas'], [('https://aadallas.org', 'Dallas Intergroup Association (AA)')]),
  ('hou', 'Houston', 'TX', 29.7604, -95.3698, 'America/Chicago', ['tx--houston'], []),
  ('dc', 'Washington', 'DC', 38.9072, -77.0369, 'America/New_York', ['dc--washington'], [('https://aa-dc.org', 'Washington Area Intergroup Association (AA)')]),
  ('phl', 'Philadelphia', 'PA', 39.9526, -75.1652, 'America/New_York', ['pa--philadelphia'], [('https://aasepia.org', 'Southeastern Pennsylvania Intergroup Association (AA)')]),
  ('atl', 'Atlanta', 'GA', 33.7490, -84.3880, 'America/New_York', ['ga--atlanta'], [('https://atlantaaa.org', 'Atlanta Central Office (AA)')]),
  ('phx', 'Phoenix', 'AZ', 33.4484, -112.0740, 'America/Phoenix', ['az--phoenix'], []),
  ('bos', 'Boston', 'MA', 42.3601, -71.0589, 'America/New_York', ['ma--boston'], []),
  ('mia', 'Miami', 'FL', 25.7617, -80.1918, 'America/New_York', ['fl--miami', 'fl--fort-lauderdale', 'fl--west-palm-beach'], []),
]
EB_QUERIES = ('sober-events', 'recovery', 'alcohol-free')
PHX_ETHOS = 'https://thephoenix.org/our-ethos'
PHX_QUOTE_RE = re.compile(r'All we ask is that anyone who participates in Phoenix-led activities has been substance free for at least 48 hours\.')
SERVICE = re.compile(r'(?i)committee|zone meeting|steering|business meeting|intergroup meeting|delegate|assembly|archives preservation|'
                     r'interphones|web ?/ ?tech|^\s*sepia noon meeting|treasurer|\bGSR\b|\bDCM\b|elections?\b|orientation|office closed|\bclosed\)|forum|corrections')
MIXED = re.compile(r"(?i)\bdrunk\b|\bhigh\b|hate being sober|\bshots?\b|liquor|whiske?y|tequila|vodka|\bbars?\b|open bar|happy hour|\bbeers?\b|\bwines?\b|\bcocktails?\b|brewery|taproom|\bpub\b|cannabis|\b420\b")
STATE_NAMES = {'new york': 'NY', 'california': 'CA', 'illinois': 'IL', 'texas': 'TX', 'district of columbia': 'DC', 'pennsylvania': 'PA',
               'georgia': 'GA', 'arizona': 'AZ', 'massachusetts': 'MA', 'florida': 'FL', 'new jersey': 'NJ', 'virginia': 'VA', 'maryland': 'MD',
               'delaware': 'DE', 'new hampshire': 'NH', 'rhode island': 'RI', 'connecticut': 'CT', 'washington dc': 'DC'}

def now(): return dt.datetime.now(dt.timezone.utc)
def stamp(): return now().strftime('%Y-%m-%dT%H:%M:%SZ')
def log(*a): print(*a, file=sys.stderr, flush=True)

def get(url, params=None, timeout=25, accept='text/html'):
    if params: url += ('&' if '?' in url else '?') + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': accept, 'Accept-Language': 'en-US,en;q=0.8'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.geturl(), r.read(3_000_000).decode('utf-8', 'replace')

def clean(s, n=None):
    s = re.sub(r'<[^>]+>', ' ', str(s or '')); s = H.unescape(s); s = re.sub(r'\s+', ' ', s).strip()
    return (s[:n - 1] + '…') if n and len(s) > n else s

def st_code(x):
    x = (x or '').strip()
    if re.fullmatch(r'[A-Za-z]{2}', x): return x.upper()
    return STATE_NAMES.get(x.lower())

def miles(a, b, c, d):
    import math
    p = math.pi / 180; h = 0.5 - math.cos((c - a) * p) / 2 + math.cos(a * p) * math.cos(c * p) * (1 - math.cos((d - b) * p)) / 2
    return 7917.5 * math.asin(math.sqrt(h))

# ---------------- The Phoenix ----------------
def phoenix_events_from(html_text):
    s = html_text.replace('\\"', '"')
    out = []
    for m in re.finditer(r'"events":\[', s):
        try: arr, _ = json.JSONDecoder().raw_decode(s, m.end() - 1)
        except Exception: continue
        if isinstance(arr, list): out += [x for x in arr if isinstance(x, dict) and x.get('id') and x.get('eventAt')]
    return out

def phoenix(metro, weeks=3):
    key, label, st, lat, lng, tz, _, _ = metro
    z = ZoneInfo(tz); seen, rows = set(), []
    d0 = dt.date.today()
    for w in range(weeks):
        wk = d0 + dt.timedelta(days=7 * w)
        p = {'locationFilter': json.dumps({'latitude': lat, 'longitude': lng, 'name': f'{label}, {st}', 'radius': 40}), 'eventTypeFilter': 'In Person',
             'seeMoreActive': 'true', 'currentPage': '1', 'mapMode': 'false', 'itemsPerPage': '100', 'timezone': tz}
        if w: p['weekStartDate'] = wk.isoformat()
        _, txt = get('https://thephoenix.org/explore-events', p, timeout=40)
        for e in phoenix_events_from(txt):
            if e['id'] in seen: continue
            seen.add(e['id'])
            if (e.get('eventType') or 'In Person') != 'In Person' or (e.get('activityType') or '') == 'Meetings': continue
            c = e.get('coordinates') or {}
            if c.get('lat') is None or miles(lat, lng, c['lat'], c['lng']) > 60: continue
            try: t0 = dt.datetime.fromisoformat(str(e['eventAt']).lstrip('$D').replace('Z', '+00:00')).astimezone(z)
            except Exception: continue
            t1 = t0 + dt.timedelta(minutes=int(e.get('duration') or 60))
            addr = e.get('locationAddress') or ''
            city, stt = (e.get('location') or ', ').rsplit(',', 1) if ',' in (e.get('location') or '') else (e.get('location') or '', '')
            zm = re.search(r'\b(\d{5})\b', addr)
            rows.append({'src': 'phoenix', 'metro': key, 'ext_id': e['id'], 'title': clean(e.get('title') or e.get('name'), 110),
                         'date': t0.date().isoformat(), 'start': t0.strftime('%H:%M'), 'end': t1.strftime('%H:%M'),
                         'venue': clean(e.get('locationName'), 80), 'address': clean(addr, 120), 'city': clean(city), 'state': st_code(stt) or st,
                         'zip': zm.group(1) if zm else None, 'lat': c.get('lat'), 'lng': c.get('lng'), 'free': True, 'price': 'Free',
                         'desc': clean(e.get('description'), 260), 'activity': e.get('activityType'),
                         'url': 'https://thephoenix.org' + e['link'] if str(e.get('link', '')).startswith('/') else e.get('link')})
        time.sleep(1.0)
    return rows

# ---------------- AA intergroup calendars (The Events Calendar REST feed) ----------------
def tribe(metro, base, org):
    key, label, st, lat, lng, tz, _, _ = metro
    rows = []
    d0 = dt.date.today(); d1 = d0 + dt.timedelta(days=HORIZON_DAYS)
    url = f'{base}/wp-json/tribe/events/v1/events'
    params = {'per_page': 50, 'start_date': d0.isoformat(), 'end_date': d1.isoformat()}
    for page in range(1, 7):
        params['page'] = page
        _, txt = get(url, params, accept='application/json')
        j = json.loads(txt)
        for e in j.get('events') or []:
            title = clean(e.get('title'), 110)
            if not title or SERVICE.search(title): continue
            if str(e.get('status') or 'publish') != 'publish': continue
            ven = e.get('venue') if isinstance(e.get('venue'), dict) else {}
            if re.search(r'(?i)\b(zoom|online|virtual)\b', str(ven.get('venue') or '')): continue   # in person only (online lists exist elsewhere)
            vs = st_code(ven.get('stateprovince') or ven.get('state') or '')
            desc = clean(e.get('description'), 400)
            sd, ed = (e.get('start_date') or '')[:16], (e.get('end_date') or '')[:16]
            try: a = dt.datetime.strptime(sd, '%Y-%m-%d %H:%M'); b = dt.datetime.strptime(ed, '%Y-%m-%d %H:%M')
            except Exception: continue
            if (b.date() - a.date()).days > 5: continue                     # long-running notices, not events
            dates = [(a.date() + dt.timedelta(days=i)).isoformat() for i in range((b.date() - a.date()).days + 1)]
            allday = str(e.get('all_day')).lower() == 'true'
            zipc = ven.get('zip') or None
            if not zipc:
                zm = re.search(r'\b[A-Z]{2}\s+(\d{5})\b', desc); zipc = zm.group(1) if zm else None
            cost = clean(e.get('cost'), 40)
            rows.append({'src': 'intergroup', 'metro': key, 'org': org, 'ext_id': str(e.get('id')), 'title': title, 'dates': dates,
                         'start': None if allday else a.strftime('%H:%M'), 'end': None if allday else b.strftime('%H:%M'),
                         'venue': clean(ven.get('venue'), 80) or None, 'address': clean(ven.get('address'), 120) or None,
                         'city': clean(ven.get('city')) or None, 'state': vs or st, 'zip': zipc,
                         'lat': float(ven['geo_lat']) if ven.get('geo_lat') else None, 'lng': float(ven['geo_lng']) if ven.get('geo_lng') else None,
                         'free': True if re.fullmatch(r'(?i)free', cost or '') else None, 'price': cost or None,
                         'desc': clean(desc, 260), 'url': e.get('url')})
        if page >= int(j.get('total_pages') or 1): break
        time.sleep(0.5)
    return rows

# ---------------- Eventbrite (discovery pages + each event's own page) ----------------
def eb_list(slug, q):
    _, txt = get(f'https://www.eventbrite.com/d/{slug}/{q}/', timeout=30)
    out = []
    for m in re.finditer(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', txt, re.S | re.I):
        try: j = json.loads(m.group(1).strip())
        except Exception: continue
        for x in (j if isinstance(j, list) else [j]):
            for it in (x.get('itemListElement') or []) if isinstance(x, dict) else []:
                ev = it.get('item') if isinstance(it, dict) else None
                if not isinstance(ev, dict) or 'Event' not in str(ev.get('@type')): continue
                if 'Online' in str(ev.get('eventAttendanceMode', '')): continue
                loc = ev.get('location') or {}; ad = loc.get('address') or {}; geo = loc.get('geo') or {}
                if (ad.get('addressCountry') or 'US') not in ('US', 'USA'): continue
                out.append({'src': 'eventbrite', 'title': clean(ev.get('name'), 110), 'sd': ev.get('startDate'), 'ed': ev.get('endDate'),
                            'venue': clean(loc.get('name'), 80), 'address': clean(ad.get('streetAddress'), 120), 'city': clean(ad.get('addressLocality')),
                            'state': st_code(ad.get('addressRegion')), 'zip': ad.get('postalCode'),
                            'lat': float(geo['latitude']) if geo.get('latitude') else None, 'lng': float(geo['longitude']) if geo.get('longitude') else None,
                            'desc': clean(ev.get('description'), 260), 'url': (ev.get('url') or '').split('?')[0]})
    return out

def eb_page(url):
    """The event's own page: start/end time, price and the host's words (same reading as events_verify.page_evidence)."""
    try: final, html = get(url, timeout=20)
    except Exception as ex: return {'error': repr(ex)[:160], 'checked_at': stamp()}
    rec = {'checked_at': stamp(), 'evidence_url': final.split('?')[0]}
    for m in re.finditer(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', html, re.S | re.I):
        try: j = json.loads(m.group(1).strip())
        except Exception: continue
        for x in (j if isinstance(j, list) else [j]):
            if isinstance(x, dict) and 'Event' in str(x.get('@type')) and x.get('startDate'):
                rec['startDate'], rec['endDate'] = x.get('startDate'), x.get('endDate')
                offs = x.get('offers') if isinstance(x.get('offers'), list) else [x.get('offers') or {}]
                try:
                    lows = [float(o.get('lowPrice', o.get('price', 'nan'))) for o in offs if isinstance(o, dict)]
                    highs = [float(o.get('highPrice', o.get('price', 'nan'))) for o in offs if isinstance(o, dict)]
                    lows = [p for p in lows if p == p]; highs = [p for p in highs if p == p]
                    if lows: rec['price_lo'], rec['price_hi'] = min(lows), max(highs or lows)
                except Exception: pass
    pieces = V._page_texts(html)
    order = {'event description': 0, 'page description': 1, 'event name': 2, 'organizer': 3, 'location': 4}
    pieces.sort(key=lambda p: order.get(p[0], 9))
    for where, text in pieces:
        mm = V.strong_match(text)
        if mm:
            org = bool(re.fullmatch(V.FELLOWSHIPS + r'|al-anon|alateen', mm.group(0), re.I))
            if org and where != 'event name': continue
            rec.update({'quote': V.sentence(text, mm), 'where': where, 'match': mm.group(0), 'org': org}); return rec
    for where, text in pieces:
        if where in ('organizer', 'location', 'event name'):
            mm = RECOVERY_ORG_RE.search(text)
            if mm: rec.update({'quote': text.strip()[:160], 'where': where, 'match': mm.group(0), 'org': True}); return rec
    rec['none'] = True
    return rec
RECOVERY_ORG_RE = V.RECOVERY_ORGS

def classify(r):
    import build_hub_data as B
    return B.classify({'title': r.get('title'), 'desc': r.get('desc'), 'venue': r.get('venue'), 'start': r.get('start')})

def fetch(force=False):
    os.makedirs(RAW, exist_ok=True)
    try:
        old = json.load(open(CACHE))
        age = (now() - dt.datetime.fromisoformat(old['fetched_at'].replace('Z', '+00:00'))).total_seconds() / 3600
        if age < FETCH_TTL_H and not force: log(f'[events-national] cache {age:.1f} h old, nothing to do'); return old
    except Exception: old = {}
    t0 = time.time(); res = {'fetched_at': stamp(), 'sources': {}, 'rows': []}
    prev = {}
    for r in old.get('rows') or []: prev.setdefault(r.get('_skey'), []).append(r)
    def keep(skey, rows, err=None):
        res['sources'][skey] = {'n': len(rows), 'error': err}
        if err and prev.get(skey): rows = prev[skey]; res['sources'][skey]['kept_previous'] = len(rows)
        for r in rows: r['_skey'] = skey
        res['rows'].extend(rows)
    # the Phoenix's own sober rule, read from its page each fetch (the evidence every Phoenix row cites)
    try:
        _, et = get(PHX_ETHOS); m = PHX_QUOTE_RE.search(clean(et))
        res['phoenix_quote'] = m.group(0) if m else None
    except Exception as ex: res['phoenix_quote'] = (old.get('phoenix_quote')); log('[phoenix ethos]', ex)
    def _fetch_metro(metro):
        out_items = []
        try: out_items.append(('phoenix:' + metro[0], phoenix(metro), None))
        except Exception as ex: out_items.append(('phoenix:' + metro[0], [], repr(ex)[:160]))
        for base, org in metro[7]:
            try: out_items.append(('intergroup:' + base.split('//')[1], tribe(metro, base, org), None))
            except Exception as ex: out_items.append(('intergroup:' + base.split('//')[1], [], repr(ex)[:160]))
        return out_items
    with cf.ThreadPoolExecutor(6) as ex:
        for items in ex.map(_fetch_metro, METROS):
            for skey, rows, err in items:
                keep(skey, rows, err)
    # Eventbrite: discovery pages with a bounded budget (Eventbrite aggressively rate-limits CI IPs)
    eb, n429 = {}, 0
    eb_deadline = time.time() + float(os.environ.get('EB_BUDGET_SEC', '45'))
    for metro in METROS:
        rows, err = [], None
        for slug in metro[6]:
            for q in EB_QUERIES:
                if n429 >= 2: err = 'rate-limited (429), stopped'; break
                if time.time() > eb_deadline: err = 'time-budget reached, kept previous'; break
                try:
                    for r in eb_list(slug, q):
                        if r['url'] and r['url'] not in eb: r['metro'] = metro[0]; eb[r['url']] = r; rows.append(r)
                except Exception as ex:
                    if '429' in str(ex): n429 += 1; time.sleep(2)
                    err = repr(ex)[:160]
                time.sleep(0.5)
            if n429 >= 2 or time.time() > eb_deadline: break
        keep('eventbrite:' + metro[0], rows, err)
    # each Eventbrite candidate that classifies as sober-looking or a healthy activity gets its own page read (cached a week, capped per run)
    try: pages = json.load(open(PAGES))
    except Exception: pages = {}
    cut = (now() - dt.timedelta(days=7)).strftime('%Y-%m-%dT%H:%M:%SZ')
    cands = [r for r in res['rows'] if r['src'] == 'eventbrite' and classify(r)[0]]
    todo = [r['url'] for r in cands if pages.get(r['url'], {}).get('checked_at', '') < cut or 'error' in pages.get(r['url'], {})][:20]
    if todo and n429 < 2:
        with cf.ThreadPoolExecutor(3) as ex:
            for u, rec in zip(todo, ex.map(eb_page, todo)): pages[u] = rec
    json.dump(pages, open(PAGES, 'w'), indent=0)
    res['eventbrite_pages_read'] = len(todo); res['seconds'] = round(time.time() - t0, 1)
    json.dump(res, open(CACHE, 'w'), indent=0)
    log(f"[events-national] fetched {len(res['rows'])} rows in {res['seconds']} s; pages read {len(todo)}")
    return res

# ---------------- build (daily) ----------------
def eb_time(iso):
    try: return dt.datetime.fromisoformat(iso)
    except Exception: return None

def build():
    t0 = time.time()
    try: res = json.load(open(CACHE))
    except Exception: log('[events-national] no cache yet'); res = {'rows': [], 'sources': {}}
    try: pages = json.load(open(PAGES))
    except Exception: pages = {}
    today = dt.date.today().isoformat(); horizon = (dt.date.today() + dt.timedelta(days=HORIZON_DAYS)).isoformat()
    phq = res.get('phoenix_quote')
    out, why_no = {}, {}
    for r in res.get('rows') or []:
        e = {k: r.get(k) for k in ('title', 'start', 'end', 'venue', 'address', 'city', 'state', 'zip', 'lat', 'lng', 'free', 'price', 'desc', 'url')}
        if r['src'] == 'eventbrite' and r.get('metro') == 'mia': continue   # South Florida Eventbrite rows go through build_hub_data.py (events.json)
        if r['src'] == 'eventbrite':
            pg = pages.get(r['url']) or {}
            a, b = eb_time(pg.get('startDate') or ''), eb_time(pg.get('endDate') or '')
            if a and 'T' in (pg.get('startDate') or ''):
                e['start'] = a.strftime('%H:%M'); e['end'] = b.strftime('%H:%M') if b else None
                sd, ed = a.date(), (b.date() if b else a.date())
            else:
                try: sd = dt.date.fromisoformat((r.get('sd') or '')[:10]); ed = dt.date.fromisoformat((r.get('ed') or r.get('sd') or '')[:10])
                except Exception: continue
            if (ed - sd).days > 5: why_no['multi-day'] = why_no.get('multi-day', 0) + 1; continue
            dates = [(sd + dt.timedelta(days=i)).isoformat() for i in range((ed - sd).days + 1)] if (ed - sd).days > 1 else [sd.isoformat()]
            if 'price_lo' in pg:
                lo, hi = pg['price_lo'], pg['price_hi']
                e['free'] = hi == 0; e['price'] = 'Free' if hi == 0 else (f'${lo:g}' if lo == hi else f'${lo:g}–${hi:g}')
            tier, why = classify(e)
            if not tier:
                if why: why_no[why] = why_no.get(why, 0) + 1
                else: why_no['no sober words / not an activity'] = why_no.get('no sober words / not an activity', 0) + 1
                continue
            e['source'] = 'Eventbrite'
            cache = {r['url']: pg} if pg.get('quote') else {}
            verify = V.auto_verify(dict(e, url=r['url']), tier, cache)
            # nationwide guard (3.6.3): a listing that also talks about drinking or getting high is not auto-verified, even when the
            # word "sober" is on its page ("Drunk / High / Sober comedy", "I hate being sober", a bar-hosted bingo); it waits for review
            blob = ' '.join(str(x or '') for x in (e.get('title'), e.get('desc'), verify.get('quote'), e.get('venue')))
            if verify.get('status') == 'verified' and MIXED.search(blob):
                verify = {'status': 'listed', 'by': 'auto', 'rule': 'sober_word_unconfirmed', 'why': 'The page says sober but also mentions alcohol or getting high; needs a person to check.', 'auto_quote': verify.get('quote'), 'evidence_url': verify.get('evidence_url')}
        elif r['src'] == 'phoenix':
            dates, tier = [r['date']], 'recovery'
            e['source'] = 'The Phoenix'
            verify = {'status': 'verified', 'by': 'auto', 'rule': 'recovery_org', 'where': 'organizer',
                      'quote': phq or 'The Phoenix: a free sober active community', 'evidence_url': PHX_ETHOS, 'checked_at': res.get('fetched_at')}
            if not phq: verify = {'status': 'listed', 'by': 'auto', 'rule': 'sober_word_unconfirmed', 'why': "The Phoenix's sober rule could not be read this week."}
        else:  # intergroup
            dates, tier = r['dates'], 'recovery'
            e['source'] = r.get('org')
            verify = {'status': 'verified', 'by': 'auto', 'rule': 'recovery_org', 'where': 'organizer',
                      'quote': f"Posted on the events calendar of {r.get('org')}", 'evidence_url': r['url'], 'checked_at': res.get('fetched_at')}
        dates = [d for d in dates if today <= d <= horizon]
        if not dates: continue
        if e.get('lat') is None and e.get('zip'):
            pt = zip_point(e['state'], e['zip'])
            if pt: e['lat'], e['lng'] = pt
        sid = V.stable_id(e)
        if sid in out:
            o = out[sid]; o['dates'] = sorted(set(o['dates']) | set(dates))[:8]; continue
        ev = {'id': sid, 'tier': 'activity' if tier == 'activity' else 'recovery', 'origin': 'web', **e, 'dates': dates[:8], 'via': r['src'], 'metro': r.get('metro'), 'verify': verify}
        out[sid] = ev
    rows = list(out.values())
    dec, extra, dec_err = V.load_decisions()
    for ev in rows: V.apply_decision(ev, dec.get(ev['id']))
    for ev in rows:
        st = ev['verify']['status']
        ev['section'] = 'sober' if st == 'verified' else 'hidden' if st == 'rejected' else 'healthy' if ev['tier'] == 'activity' else 'queue'
        for k in [k for k, v in ev.items() if v in (None, '', [])]: del ev[k]
    # South Florida (build_hub_data.py's events.json, written minutes earlier in the same refresh) joins the FL file
    try: fl = json.load(open(os.path.join(OUT, 'events.json')))
    except Exception: fl = {'events': []}
    ids = {e['id'] for e in rows}
    pub = [e for e in rows if e['section'] in ('sober', 'healthy')]
    by = {}
    for e in fl.get('events') or []:
        st = e.get('state') or 'FL'
        if e['id'] not in ids: by.setdefault(st, []).append(dict(e, state=st))
    for e in pub: by.setdefault(e.get('state') or 'FL', []).append(e)
    idx = {'generated_at': stamp(), 'version': 1, 'states': {}, 'note': 'Sober events (verified) and healthy activities by state. Other states: none collected yet; hosts can submit.',
           'sources': sorted({e.get('source') for e in pub if e.get('source')} | {'South Florida feeds (SoFlo Scene, Eventbrite, clubhouses)'}),
           'rules': fl.get('rules')}
    for f in os.listdir(OUT):
        if re.fullmatch(r'events-[a-z]{2}\.json', f): os.remove(os.path.join(OUT, f))
    for st, evs in sorted(by.items()):
        evs.sort(key=lambda x: (x['dates'][0], x.get('start') or ''))
        fn = f'events-{st.lower()}.json'
        json.dump({'generated_at': idx['generated_at'], 'state': st, 'rules': fl.get('rules'), 'events': evs}, open(os.path.join(OUT, fn), 'w'), separators=(',', ':'), ensure_ascii=False)
        idx['states'][st] = {'file': fn, 'n': len(evs), 'sober': sum(e.get('section') == 'sober' for e in evs), 'healthy': sum(e.get('section') == 'healthy' for e in evs)}
    json.dump(idx, open(os.path.join(OUT, 'events-index.json'), 'w'), separators=(',', ':'), ensure_ascii=False)
    # the admin review queue sees every national row too (listed ones wait there, as in South Florida)
    try:
        rv = json.load(open(os.path.join(RAW, 'events-review.json')))
        rv['events'] = [e for e in rv.get('events') or [] if e.get('via') not in ('phoenix', 'intergroup', 'eventbrite')] + rows
        rv['national'] = {'generated_at': idx['generated_at'], 'n': len(rows)}
        json.dump(rv, open(os.path.join(RAW, 'events-review.json'), 'w'), separators=(',', ':'), ensure_ascii=False)
    except Exception as ex: log('[events-national] review file not updated', ex)
    counts = {}
    for e in rows:
        m = e.get('metro') or '?'; c = counts.setdefault(m, {'verified': 0, 'healthy': 0, 'listed_queue': 0})
        if e['section'] == 'sober': c['verified'] += 1
        elif e['section'] == 'healthy': c['healthy'] += 1
        elif e['section'] == 'queue': c['listed_queue'] += 1
    rep = {'generated_at': idx['generated_at'], 'seconds': round(time.time() - t0, 1), 'fetched_at': res.get('fetched_at'), 'by_metro': counts,
           'by_source': {k: v for k, v in (res.get('sources') or {}).items()}, 'excluded': why_no, 'decisions_error': dec_err,
           'states': idx['states']}
    json.dump(rep, open(os.path.join(HERE, 'events_national_last.json'), 'w'), indent=1)
    log(f"[events-national] built {len(rows)} rows ({len(pub)} public) into {len(by)} state files in {rep['seconds']} s")
    return rep

_ZC = {}
def zip_point(st, z):
    st = (st or '').lower()
    if st not in _ZC:
        try: _ZC[st] = json.load(open(os.path.join(OUT, f'zips-{st}.json'))).get('zips') or {}
        except Exception: _ZC[st] = {}
    p = _ZC[st].get(str(z)[:5])
    return (p[0], p[1]) if p else None

if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'build'
    if cmd == 'fetch': fetch(force='--force' in sys.argv)
    elif cmd == 'build': print(json.dumps(build())[:3000])
