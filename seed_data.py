"""Idempotent fictional HVAC demo data for LeadLoop Ops."""

from __future__ import annotations
from datetime import UTC, datetime, timedelta
import storage


def seed_demo_data() -> None:
    storage.init_db()
    now = datetime.now(UTC)
    rows = [
        ("Sarah Mitchell", "sarah@example.com", "(555) 010-1001", "AC repair", "Urgent — no heating or cooling", "New", 0, "AC is running but the house is 82 degrees."),
        ("Daniel Brooks", "daniel@example.com", "(555) 010-1002", "Heat pump replacement", "Soon", "Estimate Sent", 3, "Comparing replacement options before summer."),
        ("Maria Thompson", "maria@example.com", "(555) 010-1003", "Seasonal maintenance", "Routine", "Follow-Up Due", 6, "Would like spring maintenance on two systems."),
        ("James Carter", "james@example.com", "(555) 010-1004", "Heating repair", "Soon", "Booked", 4, "Furnace makes a rattling noise at startup."),
        ("Ellen Price", "ellen@example.com", "(555) 010-1005", "Mini-split quote", "Routine", "Estimate Sent", 11, "Quote for a garage mini-split."),
        ("Robert Lewis", "robert@example.com", "(555) 010-1006", "Thermostat service", "Routine", "Lost", 8, "Smart thermostat installation question."),
        ("Nina Patel", "nina@example.com", "(555) 010-1007", "Heat pump replacement", "Routine", "Not Ready", 1, "Planning the replacement after a home renovation is complete."),
        ("George Wilson", "george@example.com", "(555) 010-1008", "AC repair", "Soon", "Paused", 7, "Requested no calls until returning from vacation."),
    ]
    existing = {(lead["customer_name"], lead["source"]) for lead in storage.list_leads()}
    for name,email,phone,service,urgency,status,days,description in rows:
        if (name, "Demo Website") in existing:
            continue
        lead_id = storage.create_lead(customer_name=name,email=email,phone=phone,service_type=service,
            urgency=urgency,preferred_contact_method="Email",description=description,source="Demo Website",
            status=status,created_at=(now-timedelta(days=days)).replace(microsecond=0).isoformat())
        if status == "Booked": storage.update_lead(lead_id, outcome="Booked", booked_value_estimate=1850)
        if status == "Lost": storage.update_lead(lead_id, outcome="Lost")
        if status == "Paused": storage.update_lead(lead_id, paused=1)


if __name__ == "__main__":
    seed_demo_data(); print("LeadLoop Ops demo data is ready.")
