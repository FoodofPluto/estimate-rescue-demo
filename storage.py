"""SQLite storage layer for Estimate Rescue."""

from __future__ import annotations

import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from config import get_settings
from quote_logic import default_follow_up_due_date, normalize_status


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _date_text(value: str | None) -> str:
    """Return YYYY-MM-DD from date or datetime text for resilient comparisons."""
    return str(value or "").split("T", 1)[0]


def get_connection() -> sqlite3.Connection:
    db_path = get_settings().database_path
    Path(db_path).parent.mkdir(parents=True, exist_ok=True) if Path(db_path).parent != Path(".") else None
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row else None


def init_db() -> None:
    """Create database tables if they do not exist."""
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS business_settings (
                id INTEGER PRIMARY KEY,
                business_name TEXT,
                owner_email TEXT,
                default_from_email TEXT,
                service_category TEXT,
                brand_voice TEXT,
                created_at TEXT,
                updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS message_templates (
                id INTEGER PRIMARY KEY,
                template_key TEXT UNIQUE,
                template_name TEXT,
                subject_template TEXT,
                body_template TEXT,
                created_at TEXT,
                updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS quotes (
                id INTEGER PRIMARY KEY,
                customer_name TEXT NOT NULL,
                customer_email TEXT NOT NULL,
                customer_phone TEXT,
                service_type TEXT NOT NULL,
                quote_amount REAL NOT NULL,
                quote_notes TEXT,
                quote_date TEXT NOT NULL,
                follow_up_due_date TEXT NOT NULL,
                status TEXT NOT NULL,
                source TEXT,
                public_response_token TEXT UNIQUE,
                created_at TEXT,
                updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS follow_ups (
                id INTEGER PRIMARY KEY,
                quote_id INTEGER NOT NULL,
                follow_up_type TEXT,
                message_subject TEXT,
                message_body TEXT,
                sent_to TEXT,
                delivery_status TEXT,
                sent_at TEXT,
                created_at TEXT,
                FOREIGN KEY (quote_id) REFERENCES quotes(id)
            );

            CREATE TABLE IF NOT EXISTS customer_responses (
                id INTEGER PRIMARY KEY,
                quote_id INTEGER NOT NULL,
                response_type TEXT NOT NULL,
                response_notes TEXT,
                submitted_at TEXT,
                FOREIGN KEY (quote_id) REFERENCES quotes(id)
            );

            CREATE TABLE IF NOT EXISTS activity_log (
                id INTEGER PRIMARY KEY,
                quote_id INTEGER,
                activity_type TEXT,
                activity_summary TEXT,
                created_at TEXT,
                FOREIGN KEY (quote_id) REFERENCES quotes(id)
            );
            """
        )
        # Older databases may contain quotes created before response tokens were
        # consistently assigned. Repair those rows once and persist the value.
        tokenless_ids = conn.execute(
            "SELECT id FROM quotes WHERE public_response_token IS NULL OR TRIM(public_response_token) = ''"
        ).fetchall()
        for row in tokenless_ids:
            conn.execute(
                "UPDATE quotes SET public_response_token=?, updated_at=? WHERE id=?",
                (uuid.uuid4().hex, now_iso(), row["id"]),
            )


def get_business_settings() -> dict[str, Any]:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM business_settings WHERE id = 1").fetchone()
    if row:
        return dict(row)
    return {
        "id": 1,
        "business_name": "Blue Ridge Auto Detail",
        "owner_email": get_settings().owner_email or "owner@example.com",
        "default_from_email": get_settings().resend_from_email or "",
        "service_category": "Automotive detailing",
        "brand_voice": "Friendly, helpful, and clear.",
    }


def upsert_business_settings(
    business_name: str,
    owner_email: str,
    default_from_email: str,
    service_category: str,
    brand_voice: str,
) -> None:
    stamp = now_iso()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO business_settings
                (id, business_name, owner_email, default_from_email, service_category, brand_voice, created_at, updated_at)
            VALUES (1, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                business_name=excluded.business_name,
                owner_email=excluded.owner_email,
                default_from_email=excluded.default_from_email,
                service_category=excluded.service_category,
                brand_voice=excluded.brand_voice,
                updated_at=excluded.updated_at
            """,
            (business_name, owner_email, default_from_email, service_category, brand_voice, stamp, stamp),
        )


def list_message_templates() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM message_templates ORDER BY template_name").fetchall()
    return [dict(row) for row in rows]


def upsert_message_template(
    template_key: str,
    template_name: str,
    subject_template: str,
    body_template: str,
) -> None:
    stamp = now_iso()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO message_templates
                (template_key, template_name, subject_template, body_template, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(template_key) DO UPDATE SET
                template_name=excluded.template_name,
                subject_template=excluded.subject_template,
                body_template=excluded.body_template,
                updated_at=excluded.updated_at
            """,
            (template_key, template_name, subject_template, body_template, stamp, stamp),
        )


def create_quote(
    customer_name: str,
    customer_email: str,
    customer_phone: str,
    service_type: str,
    quote_amount: float,
    quote_notes: str,
    quote_date: str,
    follow_up_due_date: str | None = None,
    status: str = "new_quote",
    source: str = "manual",
    public_response_token: str | None = None,
) -> int:
    stamp = now_iso()
    token = public_response_token or uuid.uuid4().hex
    due = follow_up_due_date or default_follow_up_due_date(quote_date)
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO quotes
                (customer_name, customer_email, customer_phone, service_type, quote_amount, quote_notes,
                 quote_date, follow_up_due_date, status, source, public_response_token, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                customer_name,
                customer_email,
                customer_phone,
                service_type,
                float(quote_amount),
                quote_notes,
                quote_date,
                due,
                normalize_status(status),
                source,
                token,
                stamp,
                stamp,
            ),
        )
        quote_id = int(cur.lastrowid)
        conn.execute(
            "INSERT INTO activity_log (quote_id, activity_type, activity_summary, created_at) VALUES (?, ?, ?, ?)",
            (quote_id, "quote_created", f"Created quote for {customer_name}.", stamp),
        )
    return quote_id


def update_quote(quote_id: int, **fields: Any) -> None:
    allowed = {
        "customer_name",
        "customer_email",
        "customer_phone",
        "service_type",
        "quote_amount",
        "quote_notes",
        "quote_date",
        "follow_up_due_date",
        "status",
        "source",
    }
    updates = {k: v for k, v in fields.items() if k in allowed}
    if "status" in updates:
        updates["status"] = normalize_status(str(updates["status"]))
    if not updates:
        return
    updates["updated_at"] = now_iso()
    clause = ", ".join(f"{key}=?" for key in updates)
    with get_connection() as conn:
        conn.execute(f"UPDATE quotes SET {clause} WHERE id=?", (*updates.values(), quote_id))


def get_quote(quote_id: int) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT q.*, COUNT(f.id) AS follow_up_count
            FROM quotes q
            LEFT JOIN follow_ups f ON f.quote_id = q.id
            WHERE q.id = ?
            GROUP BY q.id
            """,
            (quote_id,),
        ).fetchone()
    return _row_to_dict(row)


def ensure_quote_response_token(quote_id: int) -> str | None:
    """Return a quote's stable token, creating and persisting one if absent."""
    with get_connection() as conn:
        row = conn.execute("SELECT public_response_token FROM quotes WHERE id=?", (quote_id,)).fetchone()
        if not row:
            return None
        token = str(row["public_response_token"] or "").strip()
        if token:
            return token
        token = uuid.uuid4().hex
        conn.execute(
            "UPDATE quotes SET public_response_token=?, updated_at=? WHERE id=?",
            (token, now_iso(), quote_id),
        )
    return token


def get_quote_by_token(token: str) -> dict[str, Any] | None:
    if not token:
        return None
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM quotes WHERE public_response_token = ?", (token,)).fetchone()
    return _row_to_dict(row)


def list_quotes() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT q.*, COUNT(f.id) AS follow_up_count
            FROM quotes q
            LEFT JOIN follow_ups f ON f.quote_id = q.id
            GROUP BY q.id
            ORDER BY q.follow_up_due_date ASC, q.created_at DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def list_dashboard_quotes() -> list[dict[str, Any]]:
    """List real operator quotes, excluding explicitly seeded demo records."""
    return [quote for quote in list_quotes() if quote.get("source") != "demo seed"]


def list_follow_up_queue() -> list[dict[str, Any]]:
    quotes = list_quotes()
    today = datetime.now(UTC).date().isoformat()
    return [
        quote
        for quote in quotes
        if quote["status"] not in {"won", "lost"} and _date_text(quote["follow_up_due_date"]) <= today
    ]


def create_follow_up(
    quote_id: int,
    follow_up_type: str,
    message_subject: str,
    message_body: str,
    sent_to: str,
    delivery_status: str,
    sent_at: str | None = None,
) -> int:
    stamp = now_iso()
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO follow_ups
                (quote_id, follow_up_type, message_subject, message_body, sent_to, delivery_status, sent_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (quote_id, follow_up_type, message_subject, message_body, sent_to, delivery_status, sent_at, stamp),
        )
        follow_up_id = int(cur.lastrowid)
        conn.execute(
            "INSERT INTO activity_log (quote_id, activity_type, activity_summary, created_at) VALUES (?, ?, ?, ?)",
            (quote_id, "follow_up_created", f"Follow-up recorded as {delivery_status}.", stamp),
        )
    return follow_up_id


def list_follow_ups_for_quote(quote_id: int) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM follow_ups WHERE quote_id = ? ORDER BY created_at DESC", (quote_id,)).fetchall()
    return [dict(row) for row in rows]


def status_for_customer_response(response_type: str) -> str:
    """Map public customer response actions to operator quote statuses."""
    status_map = {
        "book": "customer_interested",
        "question": "customer_question",
        "deciding": "still_deciding",
        "not_interested": "lost",
    }
    return status_map.get(response_type, "still_deciding")


def create_customer_response(quote_id: int, response_type: str, response_notes: str = "") -> int:
    stamp = now_iso()
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO customer_responses (quote_id, response_type, response_notes, submitted_at)
            VALUES (?, ?, ?, ?)
            """,
            (quote_id, response_type, response_notes, stamp),
        )
        response_id = int(cur.lastrowid)
        conn.execute(
            "UPDATE quotes SET status=?, updated_at=? WHERE id=?",
            (status_for_customer_response(response_type), stamp, quote_id),
        )
        conn.execute(
            "INSERT INTO activity_log (quote_id, activity_type, activity_summary, created_at) VALUES (?, ?, ?, ?)",
            (quote_id, "customer_response", f"Customer response: {response_type}.", stamp),
        )
    return response_id


def list_customer_responses_for_quote(quote_id: int) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM customer_responses WHERE quote_id = ? ORDER BY submitted_at DESC", (quote_id,)
        ).fetchall()
    return [dict(row) for row in rows]


def add_activity(quote_id: int | None, activity_type: str, activity_summary: str) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO activity_log (quote_id, activity_type, activity_summary, created_at) VALUES (?, ?, ?, ?)",
            (quote_id, activity_type, activity_summary, now_iso()),
        )
    return int(cur.lastrowid)


def dashboard_metrics() -> dict[str, Any]:
    quotes = list_dashboard_quotes()
    open_quotes = [q for q in quotes if q["status"] not in {"won", "lost"}]
    today = datetime.now(UTC).date().isoformat()
    with get_connection() as conn:
        activity = conn.execute(
            """
            SELECT a.* FROM activity_log a
            LEFT JOIN quotes q ON q.id = a.quote_id
            WHERE q.id IS NULL OR COALESCE(q.source, '') != 'demo seed'
            ORDER BY a.created_at DESC LIMIT 8
            """
        ).fetchall()
    return {
        "open_quotes": len(open_quotes),
        "follow_ups_due_today": len([q for q in open_quotes if _date_text(q["follow_up_due_date"]) == today]),
        "overdue_quotes": len([q for q in open_quotes if _date_text(q["follow_up_due_date"]) < today]),
        "open_quote_value": sum(float(q["quote_amount"]) for q in open_quotes),
        "won_quote_value": sum(float(q["quote_amount"]) for q in quotes if q["status"] == "won"),
        "lost_quote_value": sum(float(q["quote_amount"]) for q in quotes if q["status"] == "lost"),
        "recent_activity": [dict(row) for row in activity],
    }


def seed_demo_data_if_empty() -> None:
    """Explicit development helper; the application never calls this automatically."""
    from seed_data import seed_demo_data

    with get_connection() as conn:
        count = conn.execute("SELECT COUNT(*) FROM quotes").fetchone()[0]
    if count == 0:
        seed_demo_data()
