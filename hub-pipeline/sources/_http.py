"""Tiny HTTP helpers shared by source modules (urllib, no deps)."""
import json, time, urllib.request, urllib.parse, urllib.error, gzip
UA = 'Mozilla/5.0 (Still Present Hub meeting cache; daily; contact hello@tab.bot)'
def get(url, params=None, headers=None, timeout=30, data=None, method=None):
    if params: url += ('&' if '?' in url else '?') + urllib.parse.urlencode(params, doseq=True)
    h = {'User-Agent': UA, 'Accept': '*/*', 'Accept-Encoding': 'gzip'}; h.update(headers or {})
    if isinstance(data, dict): data = urllib.parse.urlencode(data).encode()
    elif isinstance(data, str): data = data.encode()
    req = urllib.request.Request(url, headers=h, data=data, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        b = r.read()
        if r.headers.get('Content-Encoding') == 'gzip': b = gzip.decompress(b)
        return b
def get_text(url, **kw): return get(url, **kw).decode('utf-8', 'replace')
def get_json(url, retries=2, **kw):
    last = None
    for i in range(retries + 1):
        try: return json.loads(get(url, **kw))
        except Exception as e: last = e; time.sleep(1.5 * (i + 1))
    raise last
