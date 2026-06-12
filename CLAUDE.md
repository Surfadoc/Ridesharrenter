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
- `GET|POST /api/autofill` — stage/retrieve case data for bookmarklet autofill (CORS-enabled)
- `GET|POST /api/autofill/inbound` — reverse direction: "Grab" bookmarklet posts values read from an external form; the engine UI polls this every 3s and fills empty case-bar fields (never overwrites typed values)
- `GET|POST /api/autofill/maps`, `DELETE /api/autofill/maps/{id}` — field map CRUD

## Pathway JSON Schema
Requires `title`, `entry` (prompt + options where each `next` references a real pathway), and a non-empty `pathways` object. Each pathway: `title` (required), optional `steps`, `decision_points`, `destination_guidance`, `page_format`, `trigger`, `escalation_minutes`. Set-level `contacts` is optional.

## Key Behaviors
- Companion mode (`/?companion=1`, opened via the "Companion Window" topbar button) is a slim checklist/timer/contacts strip for sitting beside the EHR; CSS class `companion` on `<body>` hides library/case bar/timeline/autofill panels. Cerner is the system of record — the engine owns guidance, timing, and the protocol audit trail, not data entry.
- Selecting a triage option OR picking from the pathway dropdown opens the pathway automatically (no separate open button).
- Step completion is timestamped; per-step notes and decision answers feed the audit trail.
- Per-protocol timers escalate (amber at half `escalation_minutes`, red at the threshold; default 10 min).
- "Save Case" persists a snapshot server-side; "Export" downloads JSON; "Print" produces a summary.

## Autofill System
- Per-field copy buttons + "Copy All" for clipboard hand-off.
- Bookmarklet: stages case data to `/api/autofill`, then a bookmarklet on the target page fetches it and fills form fields using configurable CSS-selector mappings.
- Field maps stored in `data/autofill/*.json` (git-ignored — site-specific config, except the committed seed maps `cerner_transfer_center.json` and `demo_form.json`).
- Mapping selector syntax: plain CSS; `label:Some Label` matches a visible input/textarea/select by associated label text (leading `*` and case ignored — needed because most Cerner/Terra fields have no usable id or placeholder); `date:M|D|Y` handles split Terra date pickers (three |-separated selectors, value joined/split as MM/DD/YYYY).
- The bookmarklet sets values via the native value setter + input/change events so React/Terra controlled inputs (Cerner) accept them; id selectors should use stable prefixes/suffixes (`[id^=...]`, `[id$=...]`) because Cerner ids embed random per-case hashes. Pushing into Terra `- Select -` comboboxes shows text but may not register a selection — grab direction is reliable, fill of comboboxes is advisory.
- Server CORS includes `Access-Control-Allow-Private-Network: true` — without it Chrome/Edge silently block HTTPS pages (Cerner) from fetching `127.0.0.1`.
- `static/demo-form.html` is a simple test target; `static/transfercenter-cerner-mock.html` mirrors the real Cerner form structure (label wrappers, hash ids, split DOB, duplicate `#textbox` decoys) and matches the seed map's URL pattern for regression-testing selectors.
- RPA guide section covers Power Automate Desktop and AutoHotkey for desktop app targets.

## Conventions
- Keep it dependency-free and build-free. Escape any pathway-derived text inserted via innerHTML (use the `esc` helper in app.js).
