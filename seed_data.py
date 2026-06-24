"""Seed realistic demo data for Blue Ridge Auto Detail."""

from __future__ import annotations

from datetime import date, timedelta

from storage import create_follow_up, create_quote, get_connection, upsert_business_settings, upsert_message_template


def seed_demo_data() -> None:
    today = date.today()
    upsert_business_settings(
        business_name="Blue Ridge Auto Detail",
        owner_email="owner@blueridgeautodetail.example",
        default_from_email="Blue Ridge Auto Detail <quotes@example.com>",
        service_category="Automotive detailing",
        brand_voice="Helpful, clear, local, and never pushy.",
    )
    upsert_message_template(
        "first_follow_up",
        "First Follow-Up",
        "Following up on your $service_type estimate",
        (
            "Hi $customer_name,\n\n"
            "I wanted to check in on your $service_type estimate from $business_name. "
            "The quoted amount is $quote_amount.\n\n"
            "You can reply here or use this response link: $response_link"
        ),
    )

    with get_connection() as conn:
        existing_demo_quotes = conn.execute("SELECT COUNT(*) FROM quotes WHERE source = ?", ("demo seed",)).fetchone()[0]
    if existing_demo_quotes:
        return

    quotes = [
        ("Maya Thompson", "maya@example.com", "Ceramic coating", 1295, "Two-year coating for a black SUV.", -5, -2, "follow_up_due"),
        ("Jordan Lee", "jordan@example.com", "Interior deep clean", 265, "Pet hair and coffee stain cleanup.", -1, 0, "new_quote"),
        ("Sam Rivera", "sam@example.com", "Paint correction", 875, "Single-stage correction before resale.", -9, -6, "follow_up_sent"),
        ("Priya Shah", "priya@example.com", "Monthly maintenance detail", 180, "Recurring wash and interior refresh.", -14, -10, "won"),
        ("Evan Brooks", "evan@example.com", "Fleet wash inquiry", 1450, "Five service vans, exterior wash package.", -7, -4, "lost"),
    ]

    for name, email, service, amount, notes, quote_offset, due_offset, status in quotes:
        quote_id = create_quote(
            customer_name=name,
            customer_email=email,
            customer_phone="",
            service_type=service,
            quote_amount=amount,
            quote_notes=notes,
            quote_date=(today + timedelta(days=quote_offset)).isoformat(),
            follow_up_due_date=(today + timedelta(days=due_offset)).isoformat(),
            status=status,
            source="demo seed",
        )
        if status == "follow_up_sent":
            create_follow_up(
                quote_id,
                "email",
                f"Following up on your {service} estimate",
                "Demo follow-up message.",
                email,
                "sent",
                (today + timedelta(days=-5)).isoformat(),
            )


if __name__ == "__main__":
    from storage import init_db

    init_db()
    seed_demo_data()
    print("Seeded Estimate Rescue demo data.")
