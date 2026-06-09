# Transfer Center Protocol Engine Prototype

This is a standalone local prototype for a transfer-center protocol system.

## What It Does

- Runs a local backend with no external dependencies.
- Stores uploaded pathway JSON files in `data/pathways`.
- Lists available protocol sets.
- Opens a protocol set into a timed workflow.
- Supports multiple simultaneous pathway timers.
- Lets reviewers check off pathway steps.

## Run

From this folder:

```powershell
python server.py
```

Then open:

```text
http://127.0.0.1:8787
```

## Upload Format

Upload a `.json` file with this shape:

```json
{
  "id": "example_pathway",
  "title": "Example Pathway",
  "entry": {
    "id": "request_type",
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
      "steps": [
        "Open case.",
        "Contact accepting provider.",
        "Arrange transport."
      ]
    }
  }
}
```

The existing MWHC cardiac pathway is included as the first sample protocol set.

