"""Hub events: verification status per event (sober evidence), county, decisions, social + submitted items.

Statuses (event['verify']['status']):
  verified  evidence that this is a sober / recovery event:
            - rule 'host_page_says_sober': the event's own page (the host's listing) explicitly says sober, sobriety, alcohol-free,
              substance-free, in recovery, recovery community, 12-step or names a recovery fellowship. The sentence is stored as
              verify.quote and the page as verify.evidence_url, re-read at most weekly (cache raw/event_evidence.json).
            - rule 'recovery_org': run by / held at a recovery fellowship, recovery org or clubhouse (RECOVERY_ORGS below).
            - by 'admin': an admin marked it verified in /admin/events (D1 table event_reviews; optional evidence URL/quote, private note).
  listed    pulled automatically, not confirmed. Healthy activities (yoga, runs, hikes...) stay 'listed' and are shown ONLY in the
            separate "Healthy activities" section. Sober-looking listings without evidence, every social-media item and every
            host submission are 'listed' and wait in the review queue (not shown in the app until an admin verifies them).
  rejected  an admin rejected it; never shown.
Social-media items are never auto-verified (verify.by 'social', status 'listed' until an admin decides).
"""
import os, re, json, time, hashlib, datetime as dt, concurrent.futures as cf, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, 'raw')
EVID = os.path.join(RAW, 'event_evidence.json')
DECISIONS_LOCAL = os.path.join(HERE, 'event_decisions.json')
SOCIAL_CACHE = os.path.join(RAW, 'social_events.json')
DECISIONS_URL = os.environ.get('HUB_DECISIONS_URL', '')
UA = 'Mozilla/5.0 (Linux; Android 14; SM-S926B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Mobile Safari/537.36'

FELLOWSHIPS = (r"(?:alcoholics|narcotics|cocaine|crystal meth|marijuana|gamblers|overeaters|food addicts in recovery|food addicts|sex addicts|"
               r"sex and love addicts|codependents|debtors|heroin|pills|nicotine|chemically dependent) anonymous")
# words that, said by the host about the event, make it a sober / recovery event
STRONG = re.compile(r"(?i)\b(sober(?!\s+(?:up|look|reality|truth|reminder))(?:[- ]curious|[- ]friendly|ly)?|sobriety|alcohol[- ]free|booze[- ]free|"
                    r"substance[- ]free|drug[- ]free|dry (?:event|party)|in recovery|recovery (?:community|month|rally|walk|run|5k|festival|"
                    r"celebration|yoga|meditation|meeting|fellowship|support|speakers?|open mic|book club)|addiction recovery|people in recovery|"
                    r"12[- ]step|twelve[- ]step|al-anon|alateen|celebrate recovery|smart recovery|recovery dharma|refuge recovery|" + FELLOWSHIPS + r")\b")
NOT_ADDICTION = re.compile(r"(?i)\b(disaster|injury|muscle|data|economic|storm|hurricane|post[- ]surgery|wound|sports)\s+recovery|recovery (?:drink|boots|session|massage)")
# recovery fellowships / orgs / clubhouses: an event they run or host counts as a recovery event
RECOVERY_ORGS = re.compile(r"(?i)\b(" + FELLOWSHIPS + r"|al-anon|alateen|the sobe room|sobe room|4th dimension|fourth dimension|crossroads club|"
                           r"lambda south|sober today club|triangle club|alano club|easy does it club|12 ?& ?12 club|last house on the block|"
                           r"celebrate recovery|smart recovery|recovery dharma|refuge recovery|the phoenix|hanley foundation|rebel recovery|"
                           r"recovery community organization)\b")
WEAK_ONLY = re.compile(r"(?i)\b(mocktails?|zero[- ]proof|non[- ]alcoholic|n/a (?:beer|drinks))\b")

def _now(): return dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

def stable_id(e):
    k = '|'.join(re.sub(r'\W+', '', str(e.get(f) or '').lower())[:60] for f in ('title', 'venue', 'start'))
    return hashlib.md5(k.encode()).hexdigest()[:10]

def county_of(e):
    c = e.get('county')
    if c in ('Miami-Dade', 'Broward', 'Palm Beach'): return c
    lat = e.get('lat')
    if lat is None: return None
    if lat < 25.0 or lat > 27.0: return None
    return 'Miami-Dade' if lat < 25.972 else 'Broward' if lat < 26.322 else 'Palm Beach'   # county lines near the coast (approx.)

def sentence(text, m, n=220):
    a = max(text.rfind('.', 0, m.start()), text.rfind('!', 0, m.start()), text.rfind('?', 0, m.start()), text.rfind('\n', 0, m.start()))
    b = min([x for x in (text.find('.', m.end()), text.find('!', m.end()), text.find('?', m.end()), text.find('\n', m.end())) if x >= 0] or [len(text)])
    q = re.sub(r'\s+', ' ', text[a + 1:b + 1]).strip()
    if len(q) > n:
        s0 = max(0, m.start() - a - 1 - n // 2); q = ('…' if s0 else '') + q[s0:s0 + n].strip() + '…'
    return q

def strong_match(text):
    if not text or NOT_ADDICTION.search(text): return None
    m = STRONG.search(text)
    return m

def _page_texts(html):
    """(label, text) pieces of an event page that are the HOST's words: JSON-LD event name/description/organizer, meta description, og."""
    out = []
    for m in re.finditer(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', html, re.S | re.I):
        try: j = json.loads(m.group(1).strip())
        except Exception: continue
        for x in (j if isinstance(j, list) else j.get('@graph', [j]) if isinstance(j, dict) else []):
            if not isinstance(x, dict) or 'Event' not in str(x.get('@type', '')): continue
            for k in ('name', 'description'):
                if x.get(k): out.append(('event ' + k, str(x[k])))
            org = x.get('organizer')
            if isinstance(org, dict) and org.get('name'): out.append(('organizer', str(org['name'])))
            loc = x.get('location')
            if isinstance(loc, dict) and loc.get('name'): out.append(('location', str(loc['name'])))
    for m in re.finditer(r'<meta[^>]+(?:name|property)=["\'](?:description|og:description|og:title)["\'][^>]*content=["\']([^"\']+)', html, re.I):
        out.append(('page description', m.group(1)))
    import html as H
    return [(a, H.unescape(re.sub(r'<[^>]+>', ' ', b))) for a, b in out]

def fetch(url, timeout=12):
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept-Language': 'en-US,en;q=0.8'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.geturl(), r.read(1_500_000).decode('utf-8', 'replace')

def page_evidence(url):
    """Read the event's own page; return {quote, where, evidence_url} if the host's words say sober/recovery, else {none:...}."""
    try: final, html = fetch(url)
    except Exception as ex: return {'error': repr(ex)[:160]}
    pieces = _page_texts(html)
    order = {'event description': 0, 'page description': 1, 'event name': 2, 'organizer': 3, 'location': 4}
    pieces.sort(key=lambda p: order.get(p[0], 9))
    for where, text in pieces:                        # the host's own words first (description), then the name
        m = strong_match(text)
        if m:
            org = bool(re.fullmatch(FELLOWSHIPS + r'|al-anon|alateen', m.group(0), re.I))
            if org and where != 'event name': continue    # a fellowship named in passing in a description is weaker than the name / organizer
            return {'quote': sentence(text, m), 'where': where, 'evidence_url': final, 'match': m.group(0), 'org': org}
    for where, text in pieces:
        if where in ('organizer', 'location', 'event name'):
            m = RECOVERY_ORGS.search(text)
            if m: return {'quote': text.strip()[:160], 'where': where, 'evidence_url': final, 'match': m.group(0), 'org': True}
    return {'none': True, 'evidence_url': final}

def load_evidence_cache():
    try: return json.load(open(EVID))
    except Exception: return {}

def gather_evidence(events, budget=25, max_age_days=7):
    """Page evidence for each candidate (cached a week). Returns {url: record}."""
    cache = load_evidence_cache(); cut = (dt.datetime.utcnow() - dt.timedelta(days=max_age_days)).strftime('%Y-%m-%dT%H:%M:%SZ')
    todo = sorted({e['url'] for e in events if e.get('url') and (cache.get(e['url'], {}).get('checked_at', '') < cut or 'error' in cache.get(e['url'], {}))})
    t0 = time.time()
    if todo:
        ex = cf.ThreadPoolExecutor(6)
        futs = {ex.submit(page_evidence, u): u for u in todo}
        try:
            for f in cf.as_completed(futs, timeout=budget):
                r = f.result(); r['checked_at'] = _now(); cache[futs[f]] = r
        except cf.TimeoutError: pass
        ex.shutdown(wait=False, cancel_futures=True)
    os.makedirs(RAW, exist_ok=True); json.dump(cache, open(EVID, 'w'), indent=0)
    return cache, {'checked': len(todo), 'seconds': round(time.time() - t0, 1)}

def auto_verify(e, tier, cache):
    """verify dict for a web-feed event."""
    url = e.get('url')
    rec = cache.get(url) or {}
    if tier == 'recovery':
        if rec.get('quote'):
            return {'status': 'verified', 'by': 'auto', 'rule': 'recovery_org' if rec.get('org') else 'host_page_says_sober', 'quote': rec['quote'],
                    'where': rec.get('where'), 'evidence_url': rec.get('evidence_url') or url, 'checked_at': rec.get('checked_at')}
        # page not readable this run: the listing text the feed carried is the host's own words on the same page
        for where, text in (('event title', e.get('title') or ''), ('listing text', e.get('desc') or '')):
            m = strong_match(text)
            if m and not (WEAK_ONLY.search(m.group(0))):
                return {'status': 'verified', 'by': 'auto', 'rule': 'host_page_says_sober', 'quote': sentence(text, m), 'where': where,
                        'evidence_url': url, 'checked_at': _now(), 'page_read': False if rec.get('error') else None}
        for text in (e.get('title') or '', e.get('venue') or ''):
            m = RECOVERY_ORGS.search(text)
            if m: return {'status': 'verified', 'by': 'auto', 'rule': 'recovery_org', 'quote': text[:160], 'where': 'title/venue', 'evidence_url': url, 'checked_at': _now()}
        return {'status': 'listed', 'by': 'auto', 'rule': 'sober_word_unconfirmed', 'why': 'The listing looked sober but its page did not say so clearly.'}
    # healthy activity: listed unless its own page is explicitly sober / run by a recovery org
    if rec.get('quote') and not WEAK_ONLY.fullmatch(rec.get('match', '')):
        return {'status': 'verified', 'by': 'auto', 'rule': 'recovery_org' if rec.get('org') else 'host_page_says_sober', 'quote': rec['quote'],
                'where': rec.get('where'), 'evidence_url': rec.get('evidence_url') or url, 'checked_at': rec.get('checked_at')}
    return {'status': 'listed', 'by': 'auto', 'rule': 'healthy_activity', 'why': 'Healthy activity, not confirmed with the host as a sober event.'}

def load_decisions(timeout=8):
    """Admin decisions: the live D1 (public endpoint, no notes) + hub/event_decisions.json (decisions made on the box). Live wins."""
    dec, extra, err = {}, [], None
    try:
        for k, v in (json.load(open(DECISIONS_LOCAL)).get('decisions') or {}).items(): dec[k] = {**v, 'from': 'local'}
    except FileNotFoundError: pass
    except Exception as ex: err = 'local: ' + repr(ex)[:100]
    if not DECISIONS_URL:
        return dec, extra, err
    try:
        req = urllib.request.Request(DECISIONS_URL, headers={'User-Agent': 'StillPresentHubBuild/1'})
        j = json.loads(urllib.request.urlopen(req, timeout=timeout).read())
        for k, v in (j.get('decisions') or {}).items(): dec[k] = {**v, 'from': 'admin'}
        extra = j.get('extra') or []
    except Exception as ex: err = (err + '; ' if err else '') + 'live: ' + repr(ex)[:120]
    return dec, extra, err

def apply_decision(ev, d):
    if not d: return ev
    v = {'status': d['status'], 'by': 'admin', 'reviewed_at': d.get('reviewed_at'), 'auto': ev.get('verify')}
    if d.get('evidence_url'): v['evidence_url'] = d['evidence_url']
    if d.get('evidence_quote'): v['quote'] = d['evidence_quote']
    if d['status'] == 'verified' and not d.get('evidence_url') and not d.get('evidence_quote'): v['rule'] = 'confirmed_by_admin'
    ev['verify'] = v
    return ev

def load_social(today, horizon):
    """Events the weekly social fetcher found (hub/social_fetch.py -> raw/social_events.json). Always 'listed'."""
    try: j = json.load(open(SOCIAL_CACHE))
    except Exception: return [], None
    out = []
    for e in j.get('events') or []:
        dates = [d for d in (e.get('dates') or []) if today <= d <= horizon]
        if not dates: continue
        e = dict(e, dates=dates[:8]); e['id'] = e.get('id') or ('soc-' + stable_id(e)); e['origin'] = 'social'
        e['verify'] = {'status': 'listed', 'by': 'social', 'rule': 'social_never_auto', 'why': 'From a social-media account or its linked page; waiting for review.'}
        out.append(e)
    return out, {k: j.get(k) for k in ('fetched_at', 'accounts', 'channels_ok', 'channels_failed')}
