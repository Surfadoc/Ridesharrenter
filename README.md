# Transfer Center Protocol Engine

A portable prototype for a hospital transfer-center protocol system.

It moves beyond a static decision tree toward an electronic protocol engine for urgent and non-urgent calls, with uploaded pathways, active-call workspaces, timers, and parallel task tracking.

## Features

- **Guided triage** — selecting a protocol set shows its entry question; choosing an option opens the matching pathway automatically.
- **Concurrent pathways** — run several pathways on one call, each with its own escalating timer (amber → red).
- **Timestamped checklists** — every checked step records the time; add per-step notes.
- **Interactive decision points**, destination guidance, key contacts, and copy-ready page formats.
- **Audit trail** — a live case timeline of every action.
- **Save / Export / Print** — persist a case snapshot server-side, download it as JSON, or print a summary.

## Included

- `protocol_engine/server.py` — Local backend API using Python standard library only (no external dependencies).
- `protocol_engine/static/` — Browser UI (`index.html`, `styles.css`, `app.js`); no build step.
- `protocol_engine/data/pathways/` — Stored pathway JSON files including the seed MWHC cardiac pathway.
- `protocol_engine/ROADMAP.md` — Product roadmap for the protocol system.
- `mwhc-cardiac-pathway-protocol.json` — Reference copy of the MWHC cardiac pathway protocol.

## Requirements

- Python 3.8+
- A modern browser (Chrome, Edge, Firefox, Safari)

No internet connection is required after the repository is cloned.

## Quick Start

```bash
cd protocol_engine
python server.py
```

Then open: http://127.0.0.1:8787

## Uploading Pathways

Pathways are uploaded as JSON files through the browser UI. Uploaded pathways are stored in `protocol_engine/data/pathways/`.

The JSON format supports:
- Protocol set title
- Entry options (single-choice triage)
- Pathway steps (checklists)
- Page/message formats
- Decision points (yes/no branching)
- Destination guidance
- Contacts and notes

See `protocol_engine/README.md` for the upload schema.

## Important Note

This is a workflow prototype. Clinical/operational content should be reviewed, approved, versioned, and governed by the appropriate medical, operational, legal, and compliance stakeholders before live use.
