"""Deterministic LeadLoop Ops follow-up rules."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

STATUSES = ["New", "Contacted", "Estimate Sent", "Follow-Up Due", "Needs Follow-Up", "Followed Up", "Booked", "Lost", "Not Ready", "Paused"]
STOP_STATUSES = {"Booked", "Lost", "Paused"}


def parse_day(value: str | date | datetime | None) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not value:
        return datetime.now(UTC).date()
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()


def follow_up_action(lead: dict[str, Any], today: date | None = None) -> str | None:
    """Return the current required action, or None when no follow-up is due."""
    today = today or datetime.now(UTC).date()
    if lead.get("paused") or lead.get("opted_out") or lead.get("no_further_follow_up"):
        return None
    status = str(lead.get("status") or "New")
    if status in STOP_STATUSES:
        return None
    age = max((today - parse_day(lead.get("status_changed_at") or lead.get("created_at"))).days, 0)
    stage = int(lead.get("follow_up_stage") or 0)
    if status == "New":
        return "Office should respond"
    if status in {"Estimate Sent", "Follow-Up Due", "Needs Follow-Up", "Not Ready"}:
        if age >= 10 and stage < 3:
            return "Final check-in due"
        if age >= 5 and stage < 2:
            return "Follow-up 2 due"
        if age >= 2 and stage < 1:
            return "No reply after 2 days"
    return None


def is_follow_up_due(lead: dict[str, Any], today: date | None = None) -> bool:
    return follow_up_action(lead, today) is not None


def completed_stage(action: str | None) -> int:
    return {"No reply after 2 days": 1, "Follow-up 2 due": 2, "Final check-in due": 3}.get(action or "", 0)
