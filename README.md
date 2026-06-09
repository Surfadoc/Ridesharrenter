# Transfer Center Protocol Engine

A portable prototype for a hospital transfer-center protocol system.

It moves beyond a static decision tree toward an electronic protocol engine for urgent and non-urgent calls, with uploaded pathways, active-call workspaces, timers, and parallel task tracking.

## Included

- `protocol_engine/server.py` — Local backend API using Python standard library only (no external dependencies).
- `protocol_engine/static/index.html` — Browser UI for protocol library, upload, active calls, timers, and checklists.
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
