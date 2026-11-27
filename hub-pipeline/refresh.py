#!/usr/bin/env python3
"""Standalone daily Hub refresher for Still Present (Meetings + Events).
Runs cleanly in GitHub Actions with zero external dependencies beyond Python 3 stdlib.
Any individual feed failure keeps its prior cached data rather than wiping valid JSON."""
import os, sys, json, time, subprocess, datetime as dt

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.environ.get('HUB_OUT_DIR') or os.path.join(os.path.dirname(HERE), 'hub', 'data')

def run_step(name, cmd, timeout_sec, fatal=False):
    t0 = time.time()
    print(f'==> [{name}] starting: {" ".join(cmd)}', flush=True)
    env = dict(os.environ)
    env['HUB_OUT_DIR'] = OUT
    env.setdefault('HUB_SOURCE_BUDGET', '75')
    env.setdefault('HUB_EVIDENCE_BUDGET', '25')
    try:
        p = subprocess.run(cmd, cwd=HERE, env=env, timeout=timeout_sec)
        rc = p.returncode
    except subprocess.TimeoutExpired:
        print(f'!! [{name}] timed out after {timeout_sec}s (keeping prior cache)', flush=True)
        rc = 124
    except Exception as ex:
        print(f'!! [{name}] error: {ex!r}', flush=True)
        rc = 1
    dt_s = round(time.time() - t0, 1)
    print(f'<== [{name}] rc={rc} in {dt_s}s', flush=True)
    if fatal and rc != 0:
        sys.exit(rc)
    return rc

def main():
    t0 = time.time()
    # 1. Fetch national sober/recovery events (Phoenix, AA intergroups, Eventbrite) — non-fatal if rate-limited
    run_step('events-national-fetch', [sys.executable, 'events_national.py', 'fetch', '--force'], timeout_sec=180, fatal=False)

    # 2. Fetch South Florida + Online meetings and South Florida events (pulling fresh SoFlo Scene events.js)
    rc_build = run_step('build-hub-data', [sys.executable, 'build_hub_data.py', 'meetings', 'events'], timeout_sec=240, fatal=False)

    # 3. Merge refreshed South Florida meetings into meetings-fl.json & update meetings-index.json
    if rc_build == 0:
        run_step('merge-fl-index', [sys.executable, 'merge_fl_index.py'], timeout_sec=60, fatal=False)

    # 4. Build national + FL per-state events-index.json & events-<st>.json
    run_step('events-national-build', [sys.executable, 'events_national.py', 'build'], timeout_sec=90, fatal=False)

    # 5. Verify core output JSON files exist and are valid
    summary = {'finished_at': dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'), 'seconds': round(time.time() - t0, 1), 'files': {}}
    for fn in ('meetings.json', 'meetings-fl.json', 'meetings-index.json', 'events.json', 'events-index.json'):
        p = os.path.join(OUT, fn)
        if not os.path.exists(p):
            print(f'ERROR: missing required output file {fn}', file=sys.stderr)
            sys.exit(1)
        d = json.load(open(p, encoding='utf-8'))
        summary['files'][fn] = {
            'generated_at': d.get('generated_at'),
            'count': len(d.get('meetings') or d.get('rows') or d.get('events') or d.get('states') or []),
        }
    print('SUMMARY:', json.dumps(summary, indent=2), flush=True)

if __name__ == '__main__':
    main()
