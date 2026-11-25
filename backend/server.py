"""HTTP server exposing the Virtual Sales Associate REST API and frontend UI."""

from __future__ import annotations

import json
import mimetypes
import os
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, unquote, urlparse

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BACKEND_DIR)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from database import ChatbotDatabase, resolve_db_path
from engine import SalesAssociateEngine


class AppContext:
    """Shared application state initialized once for the HTTP server."""

    def __init__(
        self,
        products_path: Optional[str] = None,
        db_path: Optional[str] = None,
        frontend_dir: Optional[str] = None,
    ) -> None:
        self.products_path = products_path or os.path.join(PROJECT_ROOT, "data", "products.json")
        self.db_path = resolve_db_path(
            explicit_path=db_path,
            default_path=os.path.join(PROJECT_ROOT, "data", "chatbot.db"),
        )
        self.frontend_dir = frontend_dir or os.path.join(PROJECT_ROOT, "frontend")
        self.db = ChatbotDatabase(self.db_path)
        self.engine = SalesAssociateEngine(self.products_path, self.db)


def make_handler(app: AppContext):
    class SalesChatbotHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            # Keep server output concise
            if os.environ.get("CHATBOT_QUIET") != "1":
                super().log_message(format, *args)

        def _send_json(self, payload: Any, status: int = 200) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _read_json_body(self) -> Dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0") or "0")
            if length <= 0:
                return {}
            raw = self.rfile.read(length)
            try:
                data = json.loads(raw.decode("utf-8"))
                return data if isinstance(data, dict) else {}
            except ValueError:
                return {}

        def _serve_static(self, rel_path: str) -> None:
            if rel_path in ("", "/"):
                rel_path = "index.html"
            safe_rel = os.path.normpath(rel_path.lstrip("/"))
            if safe_rel.startswith(".."):
                self.send_error(HTTPStatus.FORBIDDEN)
                return
            full_path = os.path.join(app.frontend_dir, safe_rel)
            if not os.path.isfile(full_path):
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            mime, _ = mimetypes.guess_type(full_path)
            with open(full_path, "rb") as f:
                data = f.read()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", f"{mime or 'application/octet-stream'}; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path
            qs = parse_qs(parsed.query)

            if path == "/api/health":
                has_key = bool(
                    app.db.get_setting("gemini_api_key", "") or os.environ.get("GEMINI_API_KEY", "")
                )
                self._send_json(
                    {
                        "status": "ok",
                        "products_count": len(app.engine.products),
                        "ai_mode": "gemini-rag" if has_key else "local-hybrid",
                    }
                )
                return

            if path == "/api/products":
                q = (qs.get("q", [""])[0] or "").strip()
                cat = (qs.get("category", [""])[0] or "").strip()
                items = app.engine.products
                if cat and cat.lower() != "all":
                    items = [p for p in items if p["category"].lower() == cat.lower()]
                if q:
                    ranked = app.engine.search_products(
                        q,
                        constraints={"category": cat} if cat and cat.lower() != "all" else None,
                        top_k=24,
                    )
                    items = [m[0] for m in ranked]
                categories = sorted({p["category"] for p in app.engine.products})
                self._send_json({"products": items, "categories": categories})
                return

            if path == "/api/sessions":
                sessions = app.db.list_sessions()
                self._send_json({"sessions": sessions})
                return

            m_msgs = path.startswith("/api/sessions/") and path.endswith("/messages")
            if m_msgs:
                parts = path.strip("/").split("/")
                if len(parts) == 4:
                    session_id = unquote(parts[2])
                    session = app.db.get_session(session_id)
                    if not session:
                        self._send_json({"error": "Session not found"}, status=404)
                        return
                    messages = app.db.get_messages(session_id)
                    self._send_json({"session": session, "messages": messages})
                    return

            if path == "/api/memory":
                self._send_json(
                    {
                        "preferences": app.db.get_preferences(),
                        "recent_queries": app.db.get_recent_queries(limit=15),
                    }
                )
                return

            if path == "/api/saved":
                raw_items = app.db.list_saved_items()
                wishlist: List[Dict[str, Any]] = []
                cart: List[Dict[str, Any]] = []
                for item in raw_items:
                    prod = app.engine.product_map.get(item["product_id"])
                    if not prod:
                        continue
                    enriched = {**item, "product": prod}
                    if item["list_type"] == "cart":
                        cart.append(enriched)
                    else:
                        wishlist.append(enriched)
                cart_total = sum(i["product"]["price"] * i["quantity"] for i in cart)
                self._send_json({"wishlist": wishlist, "cart": cart, "cart_total": cart_total})
                return

            if path == "/api/settings":
                saved_key = app.db.get_setting("gemini_api_key", "")
                env_key = os.environ.get("GEMINI_API_KEY", "")
                self._send_json(
                    {
                        "gemini_configured": bool(saved_key or env_key),
                        "gemini_source": "settings" if saved_key else ("env" if env_key else "none"),
                    }
                )
                return

            if path.startswith("/api/"):
                self._send_json({"error": "Not found"}, status=404)
                return

            self._serve_static(path)

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path
            body = self._read_json_body()

            if path == "/api/sessions":
                title = str(body.get("title") or "New Shopping Chat")
                session = app.db.create_session(title=title)
                self._send_json({"session": session}, status=201)
                return

            if path == "/api/chat":
                message = str(body.get("message") or "").strip()
                if not message:
                    self._send_json({"error": "Message cannot be empty"}, status=400)
                    return
                session_id = body.get("session_id")
                if not session_id or not app.db.get_session(str(session_id)):
                    session = app.db.create_session("New Shopping Chat")
                    session_id = session["id"]
                result = app.engine.handle_message(str(session_id), message)
                self._send_json(result)
                return

            if path == "/api/memory":
                key = str(body.get("key") or "").strip()
                value = body.get("value")
                if not key or value is None or value == "":
                    self._send_json({"error": "Both key and value are required"}, status=400)
                    return
                app.db.set_preference(key, value, source="user")
                self._send_json({"preferences": app.db.get_preferences()})
                return

            if path == "/api/saved":
                list_type = str(body.get("list_type") or "wishlist")
                if list_type not in ("wishlist", "cart"):
                    self._send_json({"error": "Invalid list_type"}, status=400)
                    return
                product_ids = body.get("product_ids") or []
                if body.get("product_id"):
                    product_ids = [body["product_id"]]
                qty = int(body.get("quantity") or 1)
                added = []
                for pid in product_ids:
                    if pid in app.engine.product_map:
                        added.append(app.db.save_item(pid, list_type=list_type, quantity=qty))
                self._send_json({"added": added}, status=201)
                return

            if path == "/api/settings":
                if "gemini_api_key" in body:
                    app.db.set_setting("gemini_api_key", str(body["gemini_api_key"] or "").strip())
                saved_key = app.db.get_setting("gemini_api_key", "")
                self._send_json(
                    {
                        "gemini_configured": bool(saved_key or os.environ.get("GEMINI_API_KEY", "")),
                    }
                )
                return

            self._send_json({"error": "Not found"}, status=404)

        def do_PATCH(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path
            body = self._read_json_body()

            if path.startswith("/api/sessions/"):
                session_id = unquote(path.split("/api/sessions/", 1)[1])
                title = str(body.get("title") or "").strip()
                if not title:
                    self._send_json({"error": "Title required"}, status=400)
                    return
                updated = app.db.update_session_title(session_id, title)
                if not updated:
                    self._send_json({"error": "Session not found"}, status=404)
                    return
                self._send_json({"session": updated})
                return

            if path.startswith("/api/saved/"):
                item_id = int(path.split("/api/saved/", 1)[1])
                qty = int(body.get("quantity") or 0)
                ok = app.db.update_saved_quantity(item_id, qty)
                self._send_json({"updated": ok})
                return

            self._send_json({"error": "Not found"}, status=404)

        def do_DELETE(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path

            if path.startswith("/api/sessions/"):
                session_id = unquote(path.split("/api/sessions/", 1)[1])
                ok = app.db.delete_session(session_id)
                self._send_json({"deleted": ok})
                return

            if path == "/api/memory":
                app.db.clear_preferences()
                self._send_json({"preferences": {}})
                return

            if path.startswith("/api/memory/"):
                key = unquote(path.split("/api/memory/", 1)[1])
                ok = app.db.delete_preference(key)
                self._send_json({"deleted": ok, "preferences": app.db.get_preferences()})
                return

            if path.startswith("/api/saved/"):
                item_id = int(path.split("/api/saved/", 1)[1])
                ok = app.db.remove_saved_item(item_id)
                self._send_json({"deleted": ok})
                return

            self._send_json({"error": "Not found"}, status=404)

    return SalesChatbotHandler


def run_server(host: str = "127.0.0.1", port: int = 8000) -> None:
    app = AppContext()
    server = ThreadingHTTPServer((host, port), make_handler(app))
    print(f"Virtual Sales Associate running at http://{host}:{port}")
    print(f"Loaded {len(app.engine.products)} products | SQLite DB: {app.db_path}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        server.server_close()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    host = os.environ.get("HOST", "127.0.0.1")
    run_server(host=host, port=port)
