# Changelog

## v2.0.0 — Dashboard Redesign (2026-06-05)

### New features

**build.py**
- `compute_stats()` now produces `weekday_dist`, `cumulative_km`, `fav_type`, `yoy_cur_km`, `yoy_prev_km`, `yoy_pct_change`, and `prs` (personal records per type).
- ACWR and trend series capped at 730 entries to keep `data.json` lean.
- Scatter sample limited to 2 000 points.
- `render_dashboard()` generates a standalone HTML shell (~38 KB) that fetches `data.json` asynchronously — no more inline data embedding.

**index.html** (generated)
- Hero strip: longest streak, favourite type, YoY km, ACWR status, top distance PR.
- KPI bar: 8 at-a-glance metrics.
- Filter bar: multi-select type chips, year-range inputs, compare-last-year toggle. State persists in URL (`?types=running&from=2020&to=2026&compare=1`).
- Charts (lazy-loaded via IntersectionObserver): monthly distance line, type donut, weekday bar, cumulative area, HR-vs-distance scatter, monthly HR by type, HR distribution grouped bar, ACWR area with zone shading, 30/60/90-day load trend.
- Activity heatmap (GitHub-style, full date range).
- Personal Records cards per activity type.
- Annual Goals — add targets per type/year, progress bars backed by `localStorage`.
- Top-5 months by distance table.
- Live polling: `/api/since` checked every 60 s; new workouts shown as a toast banner.
- Manual refresh button hits `/api/refresh`.

**styles.css** (new)
- CSS custom properties for dark theme (`--bg`, `--surface`, `--primary`, `--accent`, etc.).
- Mobile-responsive grid, breakpoints at 768 px and 480 px.
- Toggle switch, modal overlay, goals grid, heatmap colour scale.

**chart.min.js** (new)
- Chart.js 4.4.0 self-hosted (205 KB) to avoid CDN availability issues.

**server.py**
- Added `/<path:filename>` catch-all route so `styles.css` and `chart.min.js` are served from the output directory.

### Bug fixes
- **Body script never executed**: top-level `let lastSeenTs = data.kpi.last_date` ran before `data` was loaded. Moved initialization into `initApp()`.
- **index.html > 500 KB**: switched from inline data to `fetch('data.json')`, reducing HTML to ~38 KB.
- **styles.css 404**: Flask was not serving static files from the project directory.
