# Still Present — Public Site, Cloudflare Proxy & Auto-Refreshing Hub

This repository powers **Still Present** on Cloudflare Pages (`https://stillpresent.pages.dev/`) and GitHub Pages (`https://aribroman.github.io/still-present-site/`).

## What's inside
- Static web app (`index.html`, `assets/`, `manifest.webmanifest`, `sw.js`, `version.json`)
- Legal & setup pages (`/privacy/`, `/delete/`, `/iphone/`)
- `_worker.js` — Cloudflare Pages Worker providing:
  - `/sb/*` pass-through proxy to Supabase (keeps Groups working even behind content filters)
  - `/hubdata/*` and `/hub/data/*` JSON delivery with CORS headers
  - `/ping` anonymous 204 health/open response
- `hub/data/` — public Meetings & Events JSON feeds
- `hub-pipeline/` + `.github/workflows/refresh-hub.yml` — automatic daily GitHub Actions job (6:00 AM ET / 11:00 UTC) that refreshes South Florida + worldwide online meetings and sober/healthy events (pulling fresh SoFlo Scene events + The Phoenix + AA intergroups) and commits updated JSON back to `main`, automatically triggering Cloudflare Pages to redeploy.

## Manual refresh
Go to **Actions → Refresh Still Present Hub (Meetings & Events) → Run workflow**.
