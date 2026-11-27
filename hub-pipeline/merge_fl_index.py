#!/usr/bin/env python3
"""Updates hub/data/meetings-fl.json and hub/data/meetings-index.json from the freshly built
South Florida meetings.json + online meeting files, while preserving all other US state files."""
import os, re, json, datetime as dt
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.environ.get('HUB_OUT_DIR') or os.path.join(os.path.dirname(HERE), 'hub', 'data')
STAMP = dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
SOFLO_BOX = (25.10, 26.98, -80.95, -79.95)
COLS = ['id', 'prog', 'name', 'day', 'time', 'end', 'att', 'loc', 'addr', 'city', 'zip',
        'lat', 'lng', 'tags', 'url', 'src', 'notes', 'join', 'venue', 'tz', 'phone', 'area']
ATT_MAP = {'in_person': 0, 'hybrid': 1, 'online': 2}
ATT_REV = {0: 'in_person', 1: 'hybrid', 2: 'online'}
SERVICE_NAME = re.compile(
    r'(?i)\b(business meeting|group conscience|area \d+ (?:assembly|committee)|district \d+ (?:committee|meeting)|'
    r'intergroup (?:board|committee|rep|meeting)|central office|steering committee|steering meeting|service committee|'
    r'general service|h&i committee|pi/cpc|convention committee)\b'
)

def in_soflo(m):
    lat, lng = m.get('lat'), m.get('lng')
    return lat is not None and lng is not None and SOFLO_BOX[0] <= lat <= SOFLO_BOX[1] and SOFLO_BOX[2] <= lng <= SOFLO_BOX[3]

def dkey(m):
    nm = re.sub(r'[^a-z0-9]+', '', (m.get('name') or '').lower())[:36]
    ad = re.sub(r'[^a-z0-9]+', '', (m.get('addr') or m.get('loc') or '').lower())[:28]
    return (m.get('prog'), m.get('day'), m.get('time'), nm, ad or (m.get('zip') or ''))

def unpack_fl(doc):
    cols = doc.get('cols') or COLS
    progs = doc.get('progs') or []
    tzs = doc.get('tzs') or ['America/New_York']
    srcs = doc.get('sources') or []
    src_meta = {s['key']: dict(s) for s in srcs if isinstance(s, dict) and s.get('key')}
    rows = []
    for r in doc.get('rows') or []:
        m = {}
        for i, c in enumerate(cols):
            m[c] = r[i] if i < len(r) else None
        if isinstance(m.get('prog'), int) and m['prog'] < len(progs):
            m['prog'] = progs[m['prog']]
        if isinstance(m.get('att'), int):
            m['att'] = ATT_REV.get(m['att'], 'in_person')
        if isinstance(m.get('tags'), str):
            m['tags'] = [t for t in m['tags'].split(',') if t]
        elif m.get('tags') is None:
            m['tags'] = []
        if isinstance(m.get('src'), int) and m['src'] < len(srcs):
            m['src'] = srcs[m['src']]['key']
        if isinstance(m.get('tz'), int) and m['tz'] < len(tzs):
            m['tz'] = tzs[m['tz']]
        else:
            m['tz'] = 'America/New_York'
        rows.append(m)
    return rows, src_meta

def main():
    rich_path = os.path.join(OUT, 'meetings.json')
    fl_path = os.path.join(OUT, 'meetings-fl.json')
    idx_path = os.path.join(OUT, 'meetings-index.json')
    if not os.path.exists(rich_path):
        raise RuntimeError('meetings.json missing')
    rich = json.load(open(rich_path, encoding='utf-8'))
    rich_keys = {s['key'] for s in rich.get('sources') or [] if s.get('key')}
    fl_rich = [dict(x, tz=x.get('tz') or 'America/New_York') for x in rich.get('meetings') or [] if x.get('att') != 'online']

    existing_non_soflo = []
    src_meta = {}
    if os.path.exists(fl_path):
        old_fl = json.load(open(fl_path, encoding='utf-8'))
        old_rows, src_meta = unpack_fl(old_fl)
        for m in old_rows:
            if not in_soflo(m) and m.get('src') not in rich_keys:
                existing_non_soflo.append(m)

    for s in rich.get('sources') or []:
        if s.get('key'):
            src_meta[s['key']] = {k: s.get(k) for k in ('key', 'name', 'program', 'page', 'feed', 'fetched_at') if s.get(k) is not None}

    combined = fl_rich + existing_non_soflo
    seen, out = set(), []
    for m in combined:
        if SERVICE_NAME.search(m.get('name') or ''):
            continue
        k = dkey(m)
        if k in seen:
            continue
        seen.add(k)
        out.append(m)
    out.sort(key=lambda m: (m.get('day') if m.get('day') is not None else 9, m.get('time') or '', m.get('name') or ''))

    progs = Counter(m.get('prog') or 'Other' for m in out)
    pl = sorted(set(m.get('prog') or 'Other' for m in out))
    tzl = sorted(set(m.get('tz') or 'America/New_York' for m in out)) or ['America/New_York']
    used = sorted({m.get('src') or 'unknown' for m in out})

    def pack(m):
        r = [m.get(c) for c in COLS]
        r[COLS.index('prog')] = pl.index(m.get('prog') or 'Other')
        r[COLS.index('att')] = ATT_MAP.get(m.get('att'), 0)
        r[COLS.index('tags')] = ','.join(m.get('tags') or []) or None
        r[COLS.index('src')] = used.index(m.get('src') or 'unknown')
        r[COLS.index('tz')] = tzl.index(m.get('tz') or 'America/New_York')
        while r and r[-1] is None:
            r.pop()
        return r

    fl_doc = {
        'generated_at': STAMP,
        'state': 'FL',
        'name': 'Florida',
        'cols': COLS,
        'progs': pl,
        'tzs': tzl,
        'sources': [
            dict(src_meta.get(k, {'key': k, 'name': k}),
                 count=sum(1 for m in out if m.get('src') == k),
                 local=sum(1 for m in out if m.get('src') == k))
            for k in used
        ],
        'venues': rich.get('venues', []),
        'rows': [pack(m) for m in out],
    }
    fl_bytes = json.dumps(fl_doc, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
    with open(fl_path, 'wb') as f:
        f.write(fl_bytes)

    if os.path.exists(idx_path):
        idx = json.load(open(idx_path, encoding='utf-8'))
        idx['generated_at'] = STAMP
        if rich.get('programs'):
            idx['programs'] = rich['programs']
        if rich.get('online_files'):
            idx['online_files'] = rich['online_files']
        if rich.get('not_included'):
            idx['not_included'] = rich['not_included']
        if 'states' in idx and 'FL' in idx['states']:
            idx['states']['FL']['n'] = len(out)
            idx['states']['FL']['bytes'] = len(fl_bytes)
            idx['states']['FL']['progs'] = dict(progs.most_common())
            idx['states']['FL']['sources'] = len(used)
        if 'counts' in idx:
            idx['counts']['local_states_total'] = sum(v.get('n', 0) for v in (idx.get('states') or {}).values())
            idx['counts']['online_worldwide'] = (rich.get('counts') or {}).get('online_worldwide', idx['counts'].get('online_worldwide'))
        with open(idx_path, 'w', encoding='utf-8') as f:
            json.dump(idx, f, separators=(',', ':'), ensure_ascii=False)

    print(json.dumps({
        'ok': True,
        'generated_at': STAMP,
        'fl_total': len(out),
        'fl_soflo_fresh': len(fl_rich),
        'fl_non_soflo_kept': len(existing_non_soflo),
    }))

if __name__ == '__main__':
    main()
