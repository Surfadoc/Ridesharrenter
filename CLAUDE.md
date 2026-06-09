# Transfer Center Protocol Engine

## Overview
Hospital transfer-center protocol system prototype. Python stdlib HTTP backend + vanilla JS/HTML/CSS frontend. No external dependencies, no build step.

## Run
```bash
cd protocol_engine && python server.py
# Opens at http://127.0.0.1:8787
```

## Architecture
- `protocol_engine/server.py` — HTTP server. JSON API for pathways and cases, plus static file serving.
- `protocol_engine/static/index.html` — markup
- `protocol_engine/static/styles.css` — styles
- `protocol_engine/static/app.js` — application logic; `state` object is the source of truth, DOM renders from it
- `protocol_engine/data/pathways/*.json` — protocol set definitions (committed seed: MWHC cardiac)
- `protocol_engine/data/cases/*.json` — saved case snapshots (git-ignored; potential PHI)

## API
- `GET /api/health`
- `GET|POST /api/pathways`, `GET|DELETE /api/pathways/{id}`
- `GET|POST /api/cases`, `GET /api/cases/{id}`

## Pathway JSON Schema
Requires `title`, `entry` (prompt + options where each `next` references a real pathway), and a non-empty `pathways` object. Each pathway: `title` (required), optional `steps`, `decision_points`, `destination_guidance`, `page_format`, `trigger`, `escalation_minutes`. Set-level `contacts` is optional.

## Key Behaviors
- Selecting a triage option OR picking from the pathway dropdown opens the pathway automatically (no separate open button).
- Step completion is timestamped; per-step notes and decision answers feed the audit trail.
- Per-protocol timers escalate (amber at half `escalation_minutes`, red at the threshold; default 10 min).
- "Save Case" persists a snapshot server-side; "Export" downloads JSON; "Print" produces a summary.

## Conventions
- Keep it dependency-free and build-free. Escape any pathway-derived text inserted via innerHTML (use the `esc` helper in app.js).
