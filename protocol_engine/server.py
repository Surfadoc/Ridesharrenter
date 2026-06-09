from __future__ import annotations

import json
import mimetypes
import re
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse


ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
DATA_DIR = ROOT / "data"
PATHWAY_DIR = DATA_DIR / "pathways"


def safe_id(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", value.strip()).strip("_").lower()
    return cleaned or "pathway"


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
    if not isinstance(payload.get("pathways"), dict) or not payload["pathways"]:
        raise ValueError("Pathway must include a non-empty pathways object.")
    if not isinstance(payload.get("entry"), dict):
        raise ValueError("Pathway must include an entry object.")

    pathway_id = safe_id(str(payload.get("id") or payload["title"]))
    payload["id"] = pathway_id
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
                "source_file": payload.get("source_file"),
                "use_note": payload.get("use_note"),
            }
        )
    return items


class ProtocolHandler(BaseHTTPRequestHandler):
    server_version = "ProtocolEngine/0.1"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)

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

        if path in {"/", "/index.html"}:
            self.send_static(STATIC_DIR / "index.html")
            return

        requested = (STATIC_DIR / path.lstrip("/")).resolve()
        if STATIC_DIR.resolve() not in requested.parents and requested != STATIC_DIR.resolve():
            self.send_error_json(HTTPStatus.FORBIDDEN, "Forbidden.")
            return
        self.send_static(requested)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/pathways":
            self.send_error_json(HTTPStatus.NOT_FOUND, "Endpoint not found.")
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            payload = json.loads(raw.decode("utf-8"))
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
        except (json.JSONDecodeError, UnicodeDecodeError):
            self.send_error_json(HTTPStatus.BAD_REQUEST, "Upload must be valid JSON.")
        except ValueError as exc:
            self.send_error_json(HTTPStatus.BAD_REQUEST, str(exc))

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        if not parsed.path.startswith("/api/pathways/"):
            self.send_error_json(HTTPStatus.NOT_FOUND, "Endpoint not found.")
            return
        pathway_id = parsed.path.rsplit("/", 1)[-1]
        path = PATHWAY_DIR / f"{safe_id(pathway_id)}.json"
        if not path.exists():
            self.send_error_json(HTTPStatus.NOT_FOUND, "Pathway not found.")
            return
        path.unlink()
        self.send_json({"ok": True})

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
    host = "127.0.0.1"
    port = 8787
    httpd = ThreadingHTTPServer((host, port), ProtocolHandler)
    print(f"Protocol Engine running at http://{host}:{port}")
    print("Press Ctrl+C to stop.")
    httpd.serve_forever()


if __name__ == "__main__":
    main()

