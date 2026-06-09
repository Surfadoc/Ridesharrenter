# Transfer Center Protocol Engine

## Overview
Hospital transfer-center protocol system prototype. Python stdlib HTTP backend + vanilla JS/HTML frontend. No external dependencies.

## Run
```bash
cd protocol_engine && python server.py
# Opens at http://127.0.0.1:8787
```

## Architecture
- `protocol_engine/server.py` — HTTP server (GET/POST/DELETE /api/pathways), serves static files
- `protocol_engine/static/index.html` — Single-page app with pathway library, case workspace, timers, checklists
- `protocol_engine/data/pathways/*.json` — Pathway data files (JSON)

## Pathway JSON Schema
Pathways require: `title` (string), `entry` (object with prompt/options), `pathways` (object of named pathway workflows). Each pathway can have `steps`, `decision_points`, `destination_guidance`, `page_format`, `trigger`.

## Key Design Points
- Zero external dependencies — Python standard library only
- Pathways stored as flat JSON files on disk
- Frontend is pure vanilla JS, no build step
- Concurrent protocol timers per active call
- Step completion tracked via checkboxes in the UI
