from __future__ import annotations

import json
import mimetypes
import re
import threading
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
AUTOFILL_DIR = DATA_DIR / "autofill"

MAX_UPLOAD_BYTES = 5 * 1024 * 1024

# In-memory staging area for autofill — holds the most-recently-staged case
# snapshot so a bookmarklet on another origin can fetch it.
_autofill_lock = threading.Lock()
_autofill_staged: dict | None = None

# Most recent capture grabbed FROM an external form (reverse direction);
# the Protocol Engine UI polls this and fills its case bar from it.
_autofill_inbound: dict | None = None


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
# Cases
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
# Autofill — field maps + staging
# ---------------------------------------------------------------------------

def load_field_maps() -> list[dict]:
    AUTOFILL_DIR.mkdir(parents=True, exist_ok=True)
    maps = []
    for path in sorted(AUTOFILL_DIR.glob("*.json")):
        try:
            maps.append(json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    return maps


def save_field_map(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("Field map must be a JSON object.")
    if not payload.get("name"):
        raise ValueError("Field map must include a name.")
    if not isinstance(payload.get("mappings"), dict) or not payload["mappings"]:
        raise ValueError("Field map must include a non-empty mappings object.")

    map_id = safe_id(payload.get("id") or payload["name"])
    payload["id"] = map_id
    payload["updated_at"] = now_iso()

    AUTOFILL_DIR.mkdir(parents=True, exist_ok=True)
    path = AUTOFILL_DIR / f"{map_id}.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def delete_field_map(map_id: str) -> bool:
    path = AUTOFILL_DIR / f"{safe_id(map_id)}.json"
    if not path.exists():
        return False
    path.unlink()
    return True


def stage_autofill(case_data: dict) -> None:
    global _autofill_staged
    with _autofill_lock:
        _autofill_staged = {
            "case_data": case_data,
            "staged_at": now_iso(),
            "maps": load_field_maps(),
        }


def get_staged_autofill() -> dict | None:
    with _autofill_lock:
        return _autofill_staged


def stage_inbound(payload: dict) -> dict:
    global _autofill_inbound
    if not isinstance(payload, dict) or not isinstance(payload.get("fields"), dict):
        raise ValueError("Inbound capture must include a fields object.")
    record = {
        "fields": {k: v.strip() for k, v in payload["fields"].items() if isinstance(v, str) and v.strip()},
        "source": str(payload.get("source") or ""),
        "captured_at": now_iso(),
    }
    if not record["fields"]:
        raise ValueError("Inbound capture contained no non-empty fields.")
    with _autofill_lock:
        _autofill_inbound = record
    return record


def get_inbound() -> dict | None:
    with _autofill_lock:
        return _autofill_inbound


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

class ProtocolHandler(BaseHTTPRequestHandler):
    server_version = "ProtocolEngine/0.3"

    def _cors_headers(self) -> None:
        """Allow cross-origin requests so the bookmarklet can reach us."""
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        # Chrome/Edge Private Network Access: HTTPS pages (e.g. Cerner) fetching
        # a loopback address are blocked unless the preflight answers with this.
        self.send_header("Access-Control-Allow-Private-Network", "true")

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self._cors_headers()
        self.send_header("Content-Length", "0")
        self.end_headers()

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

        if path == "/api/autofill":
            staged = get_staged_autofill()
            if staged:
                self.send_json(staged)
            else:
                self.send_error_json(HTTPStatus.NOT_FOUND, "No case staged for autofill. Click 'Stage for Autofill' in the Protocol Engine first.")
            return

        if path == "/api/autofill/maps":
            self.send_json({"maps": load_field_maps()})
            return

        if path == "/api/autofill/inbound":
            self.send_json({"ok": True, "inbound": get_inbound()})
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

        if path == "/api/autofill":
            self.handle_json_write(self._stage_autofill)
            return

        if path == "/api/autofill/inbound":
            self.handle_json_write(self._stage_inbound)
            return

        if path == "/api/autofill/maps":
            self.handle_json_write(self._save_field_map)
            return

        self.send_error_json(HTTPStatus.NOT_FOUND, "Endpoint not found.")

    def do_DELETE(self) -> None:
        path = urlparse(self.path).path

        if path.startswith("/api/pathways/"):
            pathway_id = path.rsplit("/", 1)[-1]
            target = PATHWAY_DIR / f"{safe_id(pathway_id)}.json"
            if not target.exists():
                self.send_error_json(HTTPStatus.NOT_FOUND, "Pathway not found.")
                return
            target.unlink()
            self.send_json({"ok": True})
            return

        if path.startswith("/api/autofill/maps/"):
            map_id = path.rsplit("/", 1)[-1]
            if delete_field_map(map_id):
                self.send_json({"ok": True})
            else:
                self.send_error_json(HTTPStatus.NOT_FOUND, "Field map not found.")
            return

        self.send_error_json(HTTPStatus.NOT_FOUND, "Endpoint not found.")

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

    def _stage_autofill(self, payload: dict) -> None:
        stage_autofill(payload)
        self.send_json({"ok": True, "staged_at": now_iso()})

    def _stage_inbound(self, payload: dict) -> None:
        record = stage_inbound(payload)
        self.send_json({"ok": True, "captured_at": record["captured_at"], "field_count": len(record["fields"])}, HTTPStatus.CREATED)

    def _save_field_map(self, payload: dict) -> None:
        fm = save_field_map(payload)
        self.send_json({"ok": True, "id": fm["id"], "name": fm["name"]}, HTTPStatus.CREATED)

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
        self._cors_headers()
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
    AUTOFILL_DIR.mkdir(parents=True, exist_ok=True)
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
