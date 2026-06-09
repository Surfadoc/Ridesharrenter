# Transfer Center Protocol Engine Prototype

A standalone local prototype for a transfer-center protocol system. No external dependencies — Python standard library only.

## What It Does

- Runs a local backend (`server.py`) serving a JSON API and the static UI.
- Stores uploaded pathway JSON files in `data/pathways/`.
- Drives a **triage flow**: selecting a protocol set shows its entry question; choosing an option **opens the matching pathway automatically**.
- Runs **multiple pathways at once**, each with its own escalating timer.
- Lets reviewers check off steps; each completion is **timestamped** and per-step **notes** are captured.
- Makes yes/no **decision points interactive** and shows destination guidance, key contacts, and page formats (with copy-to-clipboard).
- Maintains a **case timeline / audit trail** of every action.
- **Saves** a case snapshot to the server and **exports**/prints it for supervisor review.

## Run

From this folder:

```bash
python server.py
```

Then open: http://127.0.0.1:8787

## Front-end Layout

- `static/index.html` — markup only
- `static/styles.css` — styles
- `static/app.js` — application logic (vanilla JS, no build step)

## API

| Method | Path | Purpose |
| ------ | ---- | ------- |
| GET | `/api/health` | Liveness check |
| GET | `/api/pathways` | List protocol sets |
| GET | `/api/pathways/{id}` | Get one protocol set |
| POST | `/api/pathways` | Upload/replace a protocol set (validated) |
| DELETE | `/api/pathways/{id}` | Delete a protocol set |
| GET | `/api/cases` | List saved cases |
| GET | `/api/cases/{id}` | Get one saved case |
| POST | `/api/cases` | Save/update a case snapshot |

Saved cases are written to `data/cases/` and are **git-ignored** because they may contain PHI in real use.

## Upload Format

Upload a `.json` file with this shape:

```json
{
  "id": "example_pathway",
  "title": "Example Pathway",
  "contacts": { "charge_rn": "555-0100" },
  "entry": {
    "prompt": "What type of request is this?",
    "type": "single_choice",
    "options": [
      { "label": "Urgent transfer", "next": "urgent_transfer" }
    ]
  },
  "pathways": {
    "urgent_transfer": {
      "title": "Urgent Transfer",
      "trigger": "Urgent transfer request.",
      "escalation_minutes": 10,
      "steps": [
        "Open case.",
        "Contact accepting provider.",
        "Arrange transport."
      ],
      "page_format": ["URGENT TRANSFER", "Last Name, First Name"],
      "decision_points": [
        { "question": "Is the bed confirmed?", "yes": ["Proceed."], "no": ["Call bed management."] }
      ],
      "destination_guidance": {
        "icu": { "call": "555-0111", "criteria": ["Unstable"] }
      }
    }
  }
}
```

Validation rules enforced on upload:

- `title` and a non-empty `pathways` object are required.
- An `entry` object is required; every entry option `next` must point to an existing pathway (no dead ends).
- Each pathway needs a `title`; `steps` (if present) must be a list.
- `escalation_minutes` (optional) sets the timer alert threshold; the amber warning fires at half that value.

The MWHC cardiac pathway is included as the first sample protocol set.
