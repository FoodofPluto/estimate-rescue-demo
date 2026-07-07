"""SQLite storage layer for LeadLoop Ops and its Estimate Rescue workflow."""

from __future__ import annotations

import sqlite3
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from config import get_settings
from quote_logic import default_follow_up_due_date, normalize_status
from leadloop_logic import completed_stage, follow_up_action


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

            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY,
                created_at TEXT NOT NULL,
                customer_name TEXT NOT NULL,
                email TEXT NOT NULL,
                phone TEXT,
                service_type TEXT NOT NULL,
                urgency TEXT NOT NULL,
                preferred_contact_method TEXT,
                description TEXT,
                source TEXT NOT NULL DEFAULT 'Website',
                status TEXT NOT NULL DEFAULT 'New',
                status_changed_at TEXT,
                assigned_to TEXT,
                next_follow_up_at TEXT,
                follow_up_stage INTEGER NOT NULL DEFAULT 0,
                paused INTEGER NOT NULL DEFAULT 0,
                opted_out INTEGER NOT NULL DEFAULT 0,
                no_further_follow_up INTEGER NOT NULL DEFAULT 0,
                booked_value_estimate REAL,
                outcome TEXT,
                public_response_token TEXT,
                last_event_at TEXT
            );

            CREATE TABLE IF NOT EXISTS lead_events (
                id INTEGER PRIMARY KEY,
                lead_id INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                event_type TEXT NOT NULL,
                actor TEXT NOT NULL,
                message TEXT NOT NULL,
                metadata TEXT,
                FOREIGN KEY (lead_id) REFERENCES leads(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY,
                lead_id INTEGER NOT NULL,
                scheduled_at TEXT,
                sent_at TEXT,
                channel TEXT NOT NULL,
                template_name TEXT NOT NULL,
                status TEXT NOT NULL,
                preview_text TEXT NOT NULL,
                error TEXT,
                FOREIGN KEY (lead_id) REFERENCES leads(id) ON DELETE CASCADE
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
        lead_columns = {row["name"] for row in conn.execute("PRAGMA table_info(leads)").fetchall()}
        if "status_changed_at" not in lead_columns:
            conn.execute("ALTER TABLE leads ADD COLUMN status_changed_at TEXT")
        if "public_response_token" not in lead_columns:
            conn.execute("ALTER TABLE leads ADD COLUMN public_response_token TEXT")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_leads_public_response_token ON leads(public_response_token)")
        conn.execute("UPDATE leads SET status_changed_at=created_at WHERE status_changed_at IS NULL")
        tokenless_lead_ids = conn.execute(
            "SELECT id FROM leads WHERE public_response_token IS NULL OR TRIM(public_response_token) = ''"
        ).fetchall()
        for row in tokenless_lead_ids:
            conn.execute(
                "UPDATE leads SET public_response_token=? WHERE id=?",
                (uuid.uuid4().hex, row["id"]),
            )


def add_lead_event(lead_id: int, event_type: str, actor: str, message: str, metadata: str | None = None) -> int:
    stamp = now_iso()
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO lead_events (lead_id,timestamp,event_type,actor,message,metadata) VALUES (?,?,?,?,?,?)",
            (lead_id, stamp, event_type, actor, message, metadata),
        )
        conn.execute("UPDATE leads SET last_event_at=? WHERE id=?", (stamp, lead_id))
    return int(cur.lastrowid)


def create_lead(*, customer_name: str, email: str, phone: str, service_type: str, urgency: str,
                preferred_contact_method: str, description: str, source: str = "Website",
                status: str = "New", created_at: str | None = None, assigned_to: str = "Office") -> int:
    stamp = created_at or now_iso()
    token = uuid.uuid4().hex
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO leads (created_at,customer_name,email,phone,service_type,urgency,
            preferred_contact_method,description,source,status,assigned_to,next_follow_up_at,last_event_at,
            status_changed_at,public_response_token) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (stamp, customer_name.strip(), email.strip(), phone.strip(), service_type, urgency,
             preferred_contact_method, description.strip(), source, status, assigned_to, stamp, stamp, stamp, token),
        )
        lead_id = int(cur.lastrowid)
    acknowledgment = f"Thanks {customer_name.strip()}, Blue Ridge Comfort Pros received your request. Our office will follow up shortly."
    add_lead_event(lead_id, "lead_created", "System", "Web estimate request stored.")
    add_lead_event(lead_id, "acknowledgment", "System", acknowledgment)
    add_lead_event(lead_id, "internal_alert", "System", f"Office alerted: new {urgency.lower()} {service_type} lead.")
    with get_connection() as conn:
        conn.execute("""INSERT INTO messages (lead_id,scheduled_at,sent_at,channel,template_name,status,preview_text)
            VALUES (?,?,?,?,?,?,?)""", (lead_id, stamp, stamp, preferred_contact_method.lower(),
            "new_lead_acknowledgment", "simulated", acknowledgment))
    return lead_id


def list_leads(status: str | None = None) -> list[dict[str, Any]]:
    query = "SELECT * FROM leads"
    params: tuple[Any, ...] = ()
    if status and status != "All":
        query += " WHERE status=?"
        params = (status,)
    query += " ORDER BY created_at DESC"
    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def get_lead(lead_id: int) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
    return _row_to_dict(row)


def ensure_lead_response_token(lead_id: int) -> str | None:
    """Return a lead's stable public response token, creating and persisting one if absent."""
    with get_connection() as conn:
        row = conn.execute("SELECT public_response_token FROM leads WHERE id=?", (lead_id,)).fetchone()
        if not row:
            return None
        token = str(row["public_response_token"] or "").strip()
        if token:
            return token
        token = uuid.uuid4().hex
        conn.execute("UPDATE leads SET public_response_token=? WHERE id=?", (token, lead_id))
    return token


def get_lead_by_token(token: str) -> dict[str, Any] | None:
    if not token:
        return None
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM leads WHERE public_response_token = ?", (token,)).fetchone()
    return _row_to_dict(row)


def list_lead_events(lead_id: int) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM lead_events WHERE lead_id=? ORDER BY timestamp DESC,id DESC", (lead_id,)).fetchall()
    return [dict(row) for row in rows]


def list_lead_messages(lead_id: int) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM messages WHERE lead_id=? ORDER BY id DESC", (lead_id,)).fetchall()
    return [dict(row) for row in rows]


def update_lead(lead_id: int, *, actor: str = "Operator", **fields: Any) -> None:
    allowed = {"status", "assigned_to", "next_follow_up_at", "follow_up_stage", "paused",
               "booked_value_estimate", "outcome", "no_further_follow_up"}
    updates = {key: value for key, value in fields.items() if key in allowed}
    current = get_lead(lead_id)
    if not current:
        raise ValueError("Lead not found")
    updates = {key: value for key, value in updates.items() if current.get(key) != value}
    if not updates:
        return
    if "status" in updates:
        updates["status_changed_at"] = now_iso()
        if updates["status"] == "Estimate Sent":
            updates["follow_up_stage"] = 0
    clause = ", ".join(f"{key}=?" for key in updates)
    with get_connection() as conn:
        conn.execute(f"UPDATE leads SET {clause} WHERE id=?", (*updates.values(), lead_id))
    summary = ", ".join(f"{key.replace('_', ' ')}: {value}" for key, value in updates.items())
    add_lead_event(lead_id, "lead_updated", actor, summary)


def add_internal_note(lead_id: int, note: str) -> None:
    add_lead_event(lead_id, "internal_note", "Operator", note.strip())


def status_for_lead_customer_response(response_type: str) -> str:
    """Map public LeadLoop Ops response actions to operator lead statuses."""
    status_map = {
        "still_interested": "Follow-Up Due",
        "need_more_time": "Not Ready",
        "booked_elsewhere": "Lost",
        "request_follow_up": "Follow-Up Due",
    }
    return status_map.get(response_type, "Follow-Up Due")


def create_lead_customer_response(lead_id: int, response_type: str, response_notes: str = "") -> None:
    lead = get_lead(lead_id)
    if not lead:
        raise ValueError("Lead not found")
    status = status_for_lead_customer_response(response_type)
    updates: dict[str, Any] = {"status": status}
    if status == "Lost":
        updates["outcome"] = "Lost"
        updates["no_further_follow_up"] = 1
    if response_type == "request_follow_up":
        updates["next_follow_up_at"] = now_iso()
    update_lead(lead_id, actor="Customer", **updates)
    label = response_type.replace("_", " ")
    message = f"Customer response: {label}."
    if response_notes.strip():
        message = f"{message} Notes: {response_notes.strip()}"
    add_lead_event(lead_id, "customer_response", "Customer", message)


def create_simulated_follow_up(lead_id: int, preview_text: str, channel: str = "email") -> int:
    lead = get_lead(lead_id)
    if not lead:
        raise ValueError("Lead not found")
    action = follow_up_action(lead)
    stamp = now_iso()
    with get_connection() as conn:
        cur = conn.execute("""INSERT INTO messages (lead_id,scheduled_at,sent_at,channel,template_name,status,preview_text)
            VALUES (?,?,?,?,?,?,?)""", (lead_id, stamp, stamp, channel, "estimate_follow_up", "simulated", preview_text))
    add_lead_event(lead_id, "follow_up_completed", "Operator", f"{channel.title()} follow-up simulated in Demo Mode.")
    if lead["status"] == "New":
        update_lead(lead_id, status="Contacted")
    else:
        stage = max(int(lead.get("follow_up_stage") or 0), completed_stage(action))
        update_lead(lead_id, follow_up_stage=stage)
    return int(cur.lastrowid)


def list_follow_up_leads() -> list[dict[str, Any]]:
    return [lead for lead in list_leads() if follow_up_action(lead)]


def weekly_summary() -> dict[str, int]:
    cutoff = datetime.now(UTC) - timedelta(days=7)
    leads = [
        lead for lead in list_leads()
        if datetime.fromisoformat(str(lead["created_at"]).replace("Z", "+00:00")) >= cutoff
    ]
    events = [event for lead in leads for event in list_lead_events(int(lead["id"]))]
    return {
        "new_leads": len(leads),
        "acknowledged": sum(e["event_type"] == "acknowledgment" for e in events),
        "needing_follow_up": len(list_follow_up_leads()),
        "follow_ups_completed": sum(e["event_type"] == "follow_up_completed" for e in events),
        "booked": sum(lead["status"] == "Booked" for lead in leads),
        "lost": sum(lead["status"] == "Lost" for lead in leads),
        "pending": sum(lead["status"] not in {"Booked", "Lost"} for lead in leads),
    }


def reset_leadloop_demo_data() -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM messages")
        conn.execute("DELETE FROM lead_events")
        conn.execute("DELETE FROM leads")


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
        count = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
    if count == 0:
        seed_demo_data()
