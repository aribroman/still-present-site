// Present service worker (web / iPhone home-screen version only; the Android app never registers one).
// v3.5.5: every site build gets a new cache name (1795836608 is stamped by tools/build_site.sh), the new worker takes over
// at once (skipWaiting + clients.claim) and deletes every older cache. The page itself (HTML) and version.json always
// come from the network first, bypassing the browser's HTTP cache, so an update lands on the next open; the cached copy
// is only the offline fallback. Hashed files (assets/index-XXXX.js) are safe to keep, since a new build has new names.
const V = 'present-v3-1795836608'
const fresh = u => new Request(u, { cache: 'reload', credentials: 'same-origin' })
self.addEventListener('install', e => { self.skipWaiting(); e.waitUntil(caches.open(V).then(c => c.addAll(['./', './index.html', './manifest.webmanifest', './icons/icon-192.png'].map(fresh)).catch(() => {}))) })
self.addEventListener('activate', e => e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== V && k.startsWith('present-')).map(k => caches.delete(k)))).then(() => self.clients.claim())))
self.addEventListener('message', e => { if (e.data === 'skipWaiting') self.skipWaiting() })
self.addEventListener('fetch', e => {
  const u = new URL(e.request.url)
  if (e.request.method !== 'GET' || u.origin !== location.origin || u.pathname.startsWith('/api/') || u.pathname.startsWith('/wp/') || u.pathname.startsWith('/iphone') || u.pathname.startsWith('/hubdata/')) return   // v3.6: Hub data has its own offline copy (IndexedDB)
  if (u.pathname.endsWith('/version.json') || u.pathname.endsWith('/sw.js')) return   // always straight from the network
  if (e.request.mode === 'navigate' || u.pathname.endsWith('.html') || u.pathname.endsWith('/')) {
    e.respondWith(fetch(new Request(e.request.url, { cache: 'no-cache', credentials: 'same-origin' })).then(r => { if (r.ok) { const c = r.clone(); caches.open(V).then(x => x.put('./index.html', c)) } return r }).catch(() => caches.match('./index.html')))
    return
  }
  e.respondWith(caches.match(e.request).then(hit => hit || fetch(e.request).then(r => { if (r.ok) { const c = r.clone(); caches.open(V).then(x => x.put(e.request, c)) } return r })))
})
