"""Business rules for quote follow-up prioritization."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any


STATUSES = {
    "new_quote": "New Quote",
    "follow_up_due": "Follow-Up Due",
    "follow_up_sent": "Follow-Up Sent",
    "customer_interested": "Customer Interested",
    "customer_question": "Customer Question",
    "still_deciding": "Still Deciding",
    "won": "Won",
    "lost": "Lost",
    "no_response": "No Response",
}

OPEN_STATUSES = {
    "new_quote",
    "follow_up_due",
    "follow_up_sent",
    "customer_interested",
    "customer_question",
    "still_deciding",
    "no_response",
}


def parse_date(value: str | date | None) -> date:
    if isinstance(value, date):
        return value
    if not value:
        return date.today()
    return datetime.fromisoformat(str(value)).date()


def normalize_status(status: str) -> str:
    """Return a known quote status, defaulting to new_quote."""
    return status if status in STATUSES else "new_quote"


def default_follow_up_due_date(quote_date: str | date) -> str:
    """Set a default follow-up date two days after the quote date."""
    return (parse_date(quote_date) + timedelta(days=2)).isoformat()


def is_overdue(quote: dict[str, Any]) -> bool:
    return normalize_status(quote.get("status", "")) in OPEN_STATUSES and parse_date(
        quote.get("follow_up_due_date")
    ) < date.today()


def is_due_today(quote: dict[str, Any]) -> bool:
    return normalize_status(quote.get("status", "")) in OPEN_STATUSES and parse_date(
        quote.get("follow_up_due_date")
    ) == date.today()


def calculate_recovery_score(quote: dict[str, Any]) -> int:
    """Score a quote from 0 to 100 using deterministic sales follow-up signals."""
    status = normalize_status(quote.get("status", "new_quote"))
    if status == "won":
        return 100
    if status == "lost":
        return 0

    amount = float(quote.get("quote_amount") or 0)
    quote_date = parse_date(quote.get("quote_date"))
    days_since_quote = max((date.today() - quote_date).days, 0)
    previous_follow_ups = int(quote.get("follow_up_count") or 0)

    score = 25
    score += min(amount / 50, 25)
    score += max(0, 25 - abs(days_since_quote - 3) * 3)
    if is_overdue(quote):
        score += 18
    elif is_due_today(quote):
        score += 12
    if status in {"customer_interested", "customer_question"}:
        score += 20
    elif status == "still_deciding":
        score += 10
    score -= previous_follow_ups * 8

    return int(max(0, min(100, round(score))))


def suggest_next_action(quote: dict[str, Any]) -> str:
    """Return an operator-friendly next step for a quote."""
    status = normalize_status(quote.get("status", "new_quote"))
    if status == "customer_interested":
        return "Prioritize booking this customer."
    if status == "customer_question":
        return "Reply to the customer's question."
    if status == "still_deciding":
        return "Send a helpful check-in with no pressure."
    if status == "won":
        return "No action needed; quote is won."
    if status == "lost":
        return "No action needed; quote is lost."
    if is_overdue(quote):
        return "Send a follow-up today; this quote is overdue."
    if is_due_today(quote):
        return "Send the scheduled follow-up today."
    return "Monitor until the follow-up due date."


def format_currency(value: Any) -> str:
    """Format common stored and display currency values without raising."""
    if value is None:
        return "$0.00"
    try:
        normalized = str(value).strip().replace("$", "").replace(",", "")
        amount = float(normalized) if normalized else 0.0
    except (TypeError, ValueError):
        amount = 0.0
    return f"${amount:,.2f}"


def quote_selector_label(quote: dict[str, Any]) -> str:
    """Return a customer-first, unique-enough label while preserving ID lookup."""
    customer = str(quote.get("customer_name") or "").strip() or "Unnamed Customer"
    amount = format_currency(quote.get("quote_amount"))
    created = str(quote.get("created_at") or quote.get("quote_date") or "Unknown date").split("T", 1)[0]
    return f"{customer} — {amount}, {created} (Quote #{quote.get('id')})"
