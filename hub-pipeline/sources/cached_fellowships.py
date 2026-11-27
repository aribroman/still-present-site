"""Serves cached fellowship snapshots for sources whose upstream locators require a headless browser."""
import os, json

RAW = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'raw')

SOURCES = [
  {'key': 'aca', 'name': 'ACA (adultchildren.org meeting search)', 'program': 'ACA', 'scope': 'both', 'ttl_days': 3650,
   'page': 'https://adultchildren.org/meeting-search/', 'feed': 'https://adultchildren.org/meeting-search/'},
  {'key': 'coda', 'name': 'CoDA (coda.org meeting locator: Florida face-to-face + online)', 'program': 'CoDA', 'scope': 'both', 'ttl_days': 3650,
   'page': 'https://coda.org/find-a-meeting/', 'feed': 'https://coda.org/find-a-meeting/'},
  {'key': 'slaa', 'name': 'SLAA (slaafws.org meeting finder, Florida)', 'program': 'SLAA', 'scope': 'local', 'ttl_days': 3650,
   'page': 'https://slaafws.org/meetings/', 'feed': 'https://slaafws.org/meetings/'},
  {'key': 'smart', 'name': 'SMART Recovery (meetings.smartrecovery.org, South Florida)', 'program': 'SMART', 'scope': 'local', 'ttl_days': 3650,
   'page': 'https://meetings.smartrecovery.org/meetings/', 'feed': 'https://meetings.smartrecovery.org/meetings/'},
  {'key': 'cr', 'name': 'Celebrate Recovery (crlocator.com, South Florida)', 'program': 'CR', 'scope': 'local', 'ttl_days': 3650,
   'page': 'https://crlocator.com/', 'feed': 'https://crlocator.com/'},
  {'key': 'ha', 'name': 'Heroin Anonymous (heroinanonymous.org meeting list: online + hybrid)', 'program': 'HA', 'scope': 'online', 'ttl_days': 3650,
   'page': 'https://heroinanonymous.org/meetings/', 'feed': 'https://heroinanonymous.org/meetings/'},
]

def fetch(key):
    p = os.path.join(RAW, f'last_{key}.json')
    if os.path.exists(p):
        return json.load(open(p, encoding='utf-8')).get('rows') or []
    return []
