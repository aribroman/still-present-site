// Still Present — standalone Cloudflare Pages Worker
// Place this file at the root of your Cloudflare Pages static build output (alongside index.html, assets/, hub/data/, privacy/, delete/).
// Provides:
//   1. /sb/* -> transparent pass-through proxy to Supabase (lets Groups work even if a phone content filter blocks *.supabase.co)
//   2. /hubdata/* and /hub/data/* -> serves /hub/data/* JSONs with CORS headers
//   3. /ping -> anonymous 204 No Content (no logging, no storage)
//   4. Everything else -> static Pages assets (env.ASSETS)

const SB_UPSTREAM = 'https://fnabllwregqrclnzinlr.supabase.co';
const SB_REQ_HEADERS = ['apikey', 'authorization', 'content-type', 'prefer', 'x-client-info', 'accept', 'accept-profile', 'content-profile', 'range'];
const SB_RES_HEADERS = ['content-type', 'content-range', 'preference-applied', 'retry-after', 'location'];

function sbCors(request, url) {
  const origin = request.headers.get('origin');
  const h = { 'Cache-Control': 'no-store', 'Vary': 'Origin' };
  const allowed = [
    url.origin,
    'https://stillpresent.pages.dev',
    'https://appassets.androidplatform.net',
    'https://aribroman.github.io',
  ];
  if (origin && (allowed.includes(origin) || origin.endsWith('.pages.dev'))) {
    h['Access-Control-Allow-Origin'] = origin;
    h['Access-Control-Allow-Methods'] = 'GET, POST, PATCH, PUT, DELETE, OPTIONS';
    h['Access-Control-Allow-Headers'] = SB_REQ_HEADERS.join(', ');
    h['Access-Control-Expose-Headers'] = 'content-range, preference-applied, retry-after';
    h['Access-Control-Max-Age'] = '600';
  }
  return h;
}

async function sbProxy(request, url) {
  const rest = url.pathname.slice(3); // after "/sb"
  const cors = sbCors(request, url);
  if (!/^\/(auth|rest)\/v1\//.test(rest)) return new Response('Not found', { status: 404, headers: cors });
  if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: cors });
  if (!['GET', 'HEAD', 'POST', 'PATCH', 'PUT', 'DELETE'].includes(request.method)) {
    return new Response('Method not allowed', { status: 405, headers: cors });
  }
  const fwd = new Headers();
  for (const k of SB_REQ_HEADERS) {
    const v = request.headers.get(k);
    if (v !== null) fwd.set(k, v);
  }
  try {
    const r = await fetch(SB_UPSTREAM + rest + url.search, {
      method: request.method,
      headers: fwd,
      redirect: 'manual',
      body: ['GET', 'HEAD'].includes(request.method) ? undefined : await request.arrayBuffer(),
    });
    const out = new Headers(cors);
    for (const k of SB_RES_HEADERS) {
      const v = r.headers.get(k);
      if (v !== null) out.set(k, v);
    }
    out.set('X-Present-Proxy', '1');
    return new Response(r.body, { status: r.status, headers: out });
  } catch (e) {
    return new Response(JSON.stringify({ message: 'upstream_unreachable' }), {
      status: 502,
      headers: { ...cors, 'Content-Type': 'application/json' },
    });
  }
}

async function serveHubJson(request, env, mappedUrl) {
  if (request.method === 'OPTIONS') {
    return new Response(null, {
      status: 204,
      headers: {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, HEAD, OPTIONS',
        'Access-Control-Max-Age': '600',
      },
    });
  }
  const res = await env.ASSETS.fetch(new Request(mappedUrl, { method: request.method, headers: request.headers }));
  const out = new Headers(res.headers);
  out.set('Access-Control-Allow-Origin', '*');
  out.set('Cache-Control', 'public, max-age=300');
  return new Response(res.body, { status: res.status, headers: out });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === '/ping') {
      const cors = sbCors(request, url);
      return new Response(null, { status: 204, headers: cors });
    }
    if (url.pathname === '/sb' || url.pathname.startsWith('/sb/')) {
      return sbProxy(request, url);
    }
    if (url.pathname.startsWith('/hubdata/')) {
      const file = url.pathname.slice('/hubdata/'.length);
      if (/^[a-z0-9._-]+\.json$/i.test(file)) {
        return serveHubJson(request, env, new URL('/hub/data/' + file, url.origin));
      }
      return new Response('Not found', { status: 404 });
    }
    if (url.pathname.startsWith('/hub/data/')) {
      const file = url.pathname.slice('/hub/data/'.length);
      if (/^[a-z0-9._-]+\.json$/i.test(file)) {
        return serveHubJson(request, env, url);
      }
      return new Response('Not found', { status: 404 });
    }
    return env.ASSETS.fetch(request);
  },
};
