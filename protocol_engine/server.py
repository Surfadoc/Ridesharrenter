from __future__ import annotations

import json
import mimetypes
import re
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse


ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
DATA_DIR = ROOT / "data"
PATHWAY_DIR = DATA_DIR / "pathways"
CASE_DIR = DATA_DIR / "cases"

MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB guard for JSON uploads.


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def safe_id(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(value).strip()).strip("_").lower()
    return cleaned or "item"


# ---------------------------------------------------------------------------
# Pathways
# ---------------------------------------------------------------------------

def load_pathway(pathway_id: str) -> dict:
    path = PATHWAY_DIR / f"{safe_id(pathway_id)}.json"
    if not path.exists():
        raise FileNotFoundError(pathway_id)
    return json.loads(path.read_text(encoding="utf-8"))


def validate_pathway(payload: dict) -> dict:
    """Validate the shape of an uploaded protocol set and normalise its id."""
    if not isinstance(payload, dict):
        raise ValueError("Pathway must be a JSON object.")
    if not payload.get("title"):
        raise ValueError("Pathway must include a title.")

    pathways = payload.get("pathways")
    if not isinstance(pathways, dict) or not pathways:
        raise ValueError("Pathway must include a non-empty pathways object.")

    for key, pathway in pathways.items():
        if not isinstance(pathway, dict):
            raise ValueError(f"Pathway '{key}' must be an object.")
        if not pathway.get("title"):
            raise ValueError(f"Pathway '{key}' must include a title.")
        steps = pathway.get("steps")
        if steps is not None and not isinstance(steps, list):
            raise ValueError(f"Pathway '{key}' steps must be a list.")

    entry = payload.get("entry")
    if not isinstance(entry, dict):
        raise ValueError("Pathway must include an entry object.")

    # Validate that triage options point at real pathways so the UI never
    # routes a caller into a dead end.
    for option in entry.get("options", []):
        target = option.get("next")
        if target and target not in pathways:
            raise ValueError(
                f"Entry option '{option.get('label', target)}' points to unknown pathway '{target}'."
            )

    payload["id"] = safe_id(str(payload.get("id") or payload["title"]))
    payload.setdefault("updated_at", now_iso())
    return payload


def list_pathways() -> list[dict]:
    items = []
    for path in sorted(PATHWAY_DIR.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        items.append(
            {
                "id": payload.get("id") or path.stem,
                "title": payload.get("title") or path.stem,
                "pathway_count": len(payload.get("pathways", {})),
                "has_triage": bool(payload.get("entry", {}).get("options")),
                "source_file": payload.get("source_file"),
                "use_note": payload.get("use_note"),
                "updated_at": payload.get("updated_at"),
            }
        )
    return items


# ---------------------------------------------------------------------------
# Cases (audit trail / supervisor review)
# ---------------------------------------------------------------------------

def save_case(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("Case must be a JSON object.")

    case_id = safe_id(payload.get("case_id") or f"case-{datetime.now():%Y%m%d-%H%M%S}")
    payload["case_id"] = case_id

    path = CASE_DIR / f"{case_id}.json"
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
            payload.setdefault("created_at", existing.get("created_at"))
        except json.JSONDecodeError:
            pass
    payload.setdefault("created_at", now_iso())
    payload["updated_at"] = now_iso()

    CASE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def list_cases() -> list[dict]:
    items = []
    for path in sorted(CASE_DIR.glob("*.json"), reverse=True):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        items.append(
            {
                "case_id": payload.get("case_id") or path.stem,
                "patient": payload.get("patient"),
                "acuity": payload.get("acuity"),
                "protocol_count": len(payload.get("protocols", [])),
                "updated_at": payload.get("updated_at"),
            }
        )
    return items


def load_case(case_id: str) -> dict:
    path = CASE_DIR / f"{safe_id(case_id)}.json"
    if not path.exists():
        raise FileNotFoundError(case_id)
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

class ProtocolHandler(BaseHTTPRequestHandler):
    server_version = "ProtocolEngine/0.2"

    def do_GET(self) -> None:
        path = unquote(urlparse(self.path).path)

        if path == "/api/health":
            self.send_json({"ok": True, "service": "protocol-engine", "time": now_iso()})
            return

        if path == "/api/pathways":
            self.send_json({"pathways": list_pathways()})
            return

        if path.startswith("/api/pathways/"):
            pathway_id = path.rsplit("/", 1)[-1]
            try:
                self.send_json(load_pathway(pathway_id))
            except FileNotFoundError:
                self.send_error_json(HTTPStatus.NOT_FOUND, "Pathway not found.")
            return

        if path == "/api/cases":
            self.send_json({"cases": list_cases()})
            return

        if path.startswith("/api/cases/"):
            case_id = path.rsplit("/", 1)[-1]
            try:
                self.send_json(load_case(case_id))
            except FileNotFoundError:
                self.send_error_json(HTTPStatus.NOT_FOUND, "Case not found.")
            return

        if path in {"/", "/index.html"}:
            self.send_static(STATIC_DIR / "index.html")
            return

        requested = (STATIC_DIR / path.lstrip("/")).resolve()
        static_root = STATIC_DIR.resolve()
        if static_root != requested and static_root not in requested.parents:
            self.send_error_json(HTTPStatus.FORBIDDEN, "Forbidden.")
            return
        self.send_static(requested)

    def do_POST(self) -> None:
        path = urlparse(self.path).path

        if path == "/api/pathways":
            self.handle_json_write(self._create_pathway)
            return

        if path == "/api/cases":
            self.handle_json_write(self._save_case)
            return

        self.send_error_json(HTTPStatus.NOT_FOUND, "Endpoint not found.")

    def do_DELETE(self) -> None:
        path = urlparse(self.path).path
        if not path.startswith("/api/pathways/"):
            self.send_error_json(HTTPStatus.NOT_FOUND, "Endpoint not found.")
            return
        pathway_id = path.rsplit("/", 1)[-1]
        target = PATHWAY_DIR / f"{safe_id(pathway_id)}.json"
        if not target.exists():
            self.send_error_json(HTTPStatus.NOT_FOUND, "Pathway not found.")
            return
        target.unlink()
        self.send_json({"ok": True})

    # -- write helpers ------------------------------------------------------

    def handle_json_write(self, action) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length > MAX_UPLOAD_BYTES:
                self.send_error_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Upload too large.")
                return
            raw = self.rfile.read(length)
            payload = json.loads(raw.decode("utf-8"))
            action(payload)
        except (json.JSONDecodeError, UnicodeDecodeError):
            self.send_error_json(HTTPStatus.BAD_REQUEST, "Request body must be valid JSON.")
        except ValueError as exc:
            self.send_error_json(HTTPStatus.BAD_REQUEST, str(exc))

    def _create_pathway(self, payload: dict) -> None:
        pathway = validate_pathway(payload)
        PATHWAY_DIR.mkdir(parents=True, exist_ok=True)
        destination = PATHWAY_DIR / f"{pathway['id']}.json"
        destination.write_text(json.dumps(pathway, indent=2), encoding="utf-8")
        self.send_json(
            {
                "ok": True,
                "pathway": {
                    "id": pathway["id"],
                    "title": pathway["title"],
                    "pathway_count": len(pathway["pathways"]),
                },
            },
            HTTPStatus.CREATED,
        )

    def _save_case(self, payload: dict) -> None:
        case = save_case(payload)
        self.send_json({"ok": True, "case_id": case["case_id"], "updated_at": case["updated_at"]}, HTTPStatus.CREATED)

    # -- response helpers ---------------------------------------------------

    def send_static(self, path: Path) -> None:
        if not path.exists() or not path.is_file():
            self.send_error_json(HTTPStatus.NOT_FOUND, "File not found.")
            return
        content_type, _ = mimetypes.guess_type(path)
        body = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_error_json(self, status: HTTPStatus, message: str) -> None:
        self.send_json({"ok": False, "error": message}, status)

    def log_message(self, format: str, *args: object) -> None:
        print(f"{self.address_string()} - {format % args}")


def main() -> None:
    PATHWAY_DIR.mkdir(parents=True, exist_ok=True)
    CASE_DIR.mkdir(parents=True, exist_ok=True)
    host = "127.0.0.1"
    port = 8787
    httpd = ThreadingHTTPServer((host, port), ProtocolHandler)
    print(f"Protocol Engine running at http://{host}:{port}")
    print("Press Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        httpd.server_close()


if __name__ == "__main__":
    main()
