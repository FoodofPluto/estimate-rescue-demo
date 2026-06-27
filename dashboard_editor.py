"""Type-safe row preparation and persistence helpers for the dashboard editor."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from quote_logic import calculate_recovery_score, normalize_status, suggest_next_action


EDITABLE_COLUMNS = {
    "Customer": "customer_name",
    "Email": "customer_email",
    "Phone": "customer_phone",
    "Service": "service_type",
    "Amount": "quote_amount",
    "Due": "follow_up_due_date",
    "Status": "status",
    "Source": "source",
}


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def _date_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (date, datetime)):
        return value.date().isoformat() if isinstance(value, datetime) else value.isoformat()
    return str(value).split("T", 1)[0]


def _amount(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def build_dashboard_editor_rows(quotes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return homogeneous primitive values accepted by Streamlit's editor."""
    rows = []
    for quote in quotes:
        amount = _amount(quote.get("quote_amount"))
        safe_quote = dict(quote)
        safe_quote["quote_amount"] = 0.0 if amount is None else amount
        safe_quote["quote_date"] = _date_text(quote.get("quote_date"))
        safe_quote["follow_up_due_date"] = _date_text(quote.get("follow_up_due_date"))
        safe_quote["status"] = normalize_status(_text(quote.get("status")))
        rows.append({
            "_quote_id": int(quote["id"]),
            "Customer": _text(quote.get("customer_name")),
            "Email": _text(quote.get("customer_email")),
            "Phone": _text(quote.get("customer_phone")),
            "Service": _text(quote.get("service_type")),
            "Amount": amount,
            "Due": _date_text(quote.get("follow_up_due_date")),
            "Status": normalize_status(_text(quote.get("status"))),
            "Source": _text(quote.get("source")),
            "Score": str(calculate_recovery_score(safe_quote)),
            "Next action": _text(suggest_next_action(safe_quote)),
        })
    return rows


def dashboard_quote_updates(row: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """Extract only operator-editable fields from an editor result row."""
    amount = _amount(row.get("Amount"))
    return int(row["_quote_id"]), {
        "customer_name": _text(row.get("Customer")).strip() or "Unnamed Customer",
        "customer_email": _text(row.get("Email")).strip(),
        "customer_phone": _text(row.get("Phone")).strip(),
        "service_type": _text(row.get("Service")).strip(),
        "quote_amount": 0.0 if amount is None else amount,
        "follow_up_due_date": _date_text(row.get("Due")),
        "status": normalize_status(_text(row.get("Status"))),
        "source": _text(row.get("Source")).strip(),
    }
