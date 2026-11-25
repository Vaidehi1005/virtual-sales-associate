"""SQLite persistence layer for the Virtual Sales Associate chatbot.

Stores conversation sessions, message history, session-level shopping context,
cross-session user preferences/memory, wishlist/cart items, and settings.
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def resolve_db_path(
    explicit_path: Optional[str] = None,
    default_path: Optional[str] = None,
) -> str:
    """Resolve the SQLite database path from explicit argument, env var, or default.

    Checks ``explicit_path`` first, then the ``CHATBOT_DB_PATH`` environment
    variable, and finally falls back to ``default_path`` (or ``data/chatbot.db``
    under the project root).
    """
    chosen = (
        (explicit_path or "").strip()
        or os.environ.get("CHATBOT_DB_PATH", "").strip()
        or (default_path or "").strip()
    )
    if not chosen:
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        chosen = os.path.join(project_root, "data", "chatbot.db")
    return os.path.abspath(os.path.expanduser(chosen))


class ChatbotDatabase:
    """Thread-safe SQLite repository for all persistent chatbot data."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=15.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    context_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_messages_session_id
                    ON messages(session_id, id);

                CREATE TABLE IF NOT EXISTS user_preferences (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'inferred',
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS saved_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_id TEXT NOT NULL,
                    list_type TEXT NOT NULL CHECK(list_type IN ('wishlist', 'cart')),
                    quantity INTEGER NOT NULL DEFAULT 1,
                    note TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    UNIQUE(product_id, list_type)
                );

                CREATE TABLE IF NOT EXISTS app_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS query_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    query TEXT NOT NULL,
                    intent TEXT,
                    matched_product_ids TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL
                );
                """
            )

    # ------------------------------------------------------------------
    # Sessions
    # ------------------------------------------------------------------

    def create_session(self, title: str = "New Shopping Chat") -> Dict[str, Any]:
        session_id = str(uuid.uuid4())
        now = _utc_now()
        default_ctx: Dict[str, Any] = {
            "budget_min": None,
            "budget_max": None,
            "active_category": None,
            "active_subcategory": None,
            "preferred_brands": [],
            "preferred_colors": [],
            "use_cases": [],
            "last_product_ids": [],
            "last_compared_ids": [],
            "last_intent": None,
            "last_query": None,
            "pending_clarification": None,
        }
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO sessions (id, title, created_at, updated_at, context_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, title, now, now, json.dumps(default_ctx)),
            )
        return self.get_session(session_id)  # type: ignore[return-value]

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT s.*,
                       (SELECT COUNT(*) FROM messages m WHERE m.session_id = s.id) AS message_count
                FROM sessions s
                WHERE s.id = ?
                """,
                (session_id,),
            ).fetchone()
        if not row:
            return None
        return self._row_to_session(row)

    def list_sessions(self) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT s.*,
                       (SELECT COUNT(*) FROM messages m WHERE m.session_id = s.id) AS message_count,
                       (SELECT content FROM messages m WHERE m.session_id = s.id ORDER BY m.id DESC LIMIT 1) AS last_message
                FROM sessions s
                ORDER BY s.updated_at DESC
                """
            ).fetchall()
        result: List[Dict[str, Any]] = []
        for row in rows:
            item = self._row_to_session(row)
            item["last_message"] = row["last_message"] or ""
            result.append(item)
        return result

    def update_session_title(self, session_id: str, title: str) -> Optional[Dict[str, Any]]:
        now = _utc_now()
        with self._connect() as conn:
            conn.execute(
                "UPDATE sessions SET title = ?, updated_at = ? WHERE id = ?",
                (title.strip()[:80] or "Shopping Chat", now, session_id),
            )
        return self.get_session(session_id)

    def update_session_context(self, session_id: str, context: Dict[str, Any]) -> None:
        now = _utc_now()
        with self._connect() as conn:
            conn.execute(
                "UPDATE sessions SET context_json = ?, updated_at = ? WHERE id = ?",
                (json.dumps(context), now, session_id),
            )

    def delete_session(self, session_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        return cur.rowcount > 0

    @staticmethod
    def _row_to_session(row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "id": row["id"],
            "title": row["title"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "context": json.loads(row["context_json"] or "{}"),
            "message_count": row["message_count"] if "message_count" in row.keys() else 0,
        }

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        now = _utc_now()
        meta_json = json.dumps(metadata or {})
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO messages (session_id, role, content, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, role, content, meta_json, now),
            )
            conn.execute(
                "UPDATE sessions SET updated_at = ? WHERE id = ?",
                (now, session_id),
            )
            msg_id = cur.lastrowid
        return {
            "id": msg_id,
            "session_id": session_id,
            "role": role,
            "content": content,
            "metadata": metadata or {},
            "created_at": now,
        }

    def get_messages(self, session_id: str, limit: int = 200) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, session_id, role, content, metadata_json, created_at
                FROM messages
                WHERE session_id = ?
                ORDER BY id ASC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
        return [
            {
                "id": r["id"],
                "session_id": r["session_id"],
                "role": r["role"],
                "content": r["content"],
                "metadata": json.loads(r["metadata_json"] or "{}"),
                "created_at": r["created_at"],
            }
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Cross-session Persistent User Memory / Preferences
    # ------------------------------------------------------------------

    def set_preference(self, key: str, value: Any, source: str = "inferred") -> None:
        now = _utc_now()
        serialized = json.dumps(value) if not isinstance(value, str) else value
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO user_preferences (key, value, source, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    source = excluded.source,
                    updated_at = excluded.updated_at
                """,
                (key, serialized, source, now),
            )

    def get_preferences(self) -> Dict[str, Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT key, value, source, updated_at FROM user_preferences ORDER BY updated_at DESC"
            ).fetchall()
        prefs: Dict[str, Dict[str, Any]] = {}
        for r in rows:
            val: Any = r["value"]
            try:
                val = json.loads(val)
            except (ValueError, TypeError):
                pass
            prefs[r["key"]] = {
                "value": val,
                "source": r["source"],
                "updated_at": r["updated_at"],
            }
        return prefs

    def delete_preference(self, key: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM user_preferences WHERE key = ?", (key,))
        return cur.rowcount > 0

    def clear_preferences(self) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM user_preferences")

    # ------------------------------------------------------------------
    # Saved Items (Wishlist & Cart)
    # ------------------------------------------------------------------

    def save_item(
        self,
        product_id: str,
        list_type: str = "wishlist",
        quantity: int = 1,
        note: str = "",
    ) -> Dict[str, Any]:
        now = _utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO saved_items (product_id, list_type, quantity, note, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(product_id, list_type) DO UPDATE SET
                    quantity = saved_items.quantity + excluded.quantity,
                    note = CASE WHEN excluded.note != '' THEN excluded.note ELSE saved_items.note END
                """,
                (product_id, list_type, max(1, quantity), note, now),
            )
            row = conn.execute(
                "SELECT * FROM saved_items WHERE product_id = ? AND list_type = ?",
                (product_id, list_type),
            ).fetchone()
        return dict(row)

    def update_saved_quantity(self, item_id: int, quantity: int) -> bool:
        if quantity <= 0:
            return self.remove_saved_item(item_id)
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE saved_items SET quantity = ? WHERE id = ?",
                (quantity, item_id),
            )
        return cur.rowcount > 0

    def list_saved_items(self, list_type: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            if list_type:
                rows = conn.execute(
                    "SELECT * FROM saved_items WHERE list_type = ? ORDER BY created_at DESC",
                    (list_type,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM saved_items ORDER BY created_at DESC"
                ).fetchall()
        return [dict(r) for r in rows]

    def remove_saved_item(self, item_id: int) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM saved_items WHERE id = ?", (item_id,))
        return cur.rowcount > 0

    def clear_saved_items(self, list_type: Optional[str] = None) -> None:
        with self._connect() as conn:
            if list_type:
                conn.execute("DELETE FROM saved_items WHERE list_type = ?", (list_type,))
            else:
                conn.execute("DELETE FROM saved_items")

    # ------------------------------------------------------------------
    # Settings & Query Logs
    # ------------------------------------------------------------------

    def set_setting(self, key: str, value: str) -> None:
        now = _utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO app_settings (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                (key, value, now),
            )

    def get_setting(self, key: str, default: str = "") -> str:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value FROM app_settings WHERE key = ?", (key,)
            ).fetchone()
        return row["value"] if row else default

    def log_query(
        self, session_id: str, query: str, intent: str, matched_product_ids: List[str]
    ) -> None:
        now = _utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO query_logs (session_id, query, intent, matched_product_ids, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, query, intent, json.dumps(matched_product_ids), now),
            )

    def get_recent_queries(self, limit: int = 20) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM query_logs ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [
            {
                "id": r["id"],
                "session_id": r["session_id"],
                "query": r["query"],
                "intent": r["intent"],
                "matched_product_ids": json.loads(r["matched_product_ids"] or "[]"),
                "created_at": r["created_at"],
            }
            for r in rows
        ]
