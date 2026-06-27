from datetime import date, datetime, UTC

from dashboard_editor import build_dashboard_editor_rows, dashboard_quote_updates


def test_dashboard_rows_normalize_created_quote_values():
    quote = {
        "id": 42,
        "customer_name": "Morgan",
        "customer_email": "morgan@example.com",
        "customer_phone": None,
        "service_type": "Detail",
        "quote_amount": "1200.50",
        "quote_date": "2026-06-20",
        "follow_up_due_date": datetime(2026, 6, 29, 14, 30, tzinfo=UTC),
        "status": "new_quote",
        "source": None,
        "follow_up_count": None,
        "created_at": datetime.now(UTC),
        "public_response_token": "protected",
    }

    row = build_dashboard_editor_rows([quote])[0]

    assert row["_quote_id"] == 42
    assert row["Amount"] == 1200.5
    assert row["Due"] == "2026-06-29"
    assert row["Phone"] == row["Source"] == ""
    assert isinstance(row["Score"], str)
    assert "created_at" not in row
    assert "public_response_token" not in row


def test_dashboard_rows_handle_missing_optional_and_bad_amount_values():
    quote = {
        "id": "7",
        "customer_name": None,
        "quote_amount": "$1,200",
        "quote_date": date(2026, 6, 20),
        "follow_up_due_date": None,
        "status": None,
    }

    row = build_dashboard_editor_rows([quote])[0]

    assert row["Customer"] == ""
    assert row["Amount"] is None
    assert row["Due"] == ""
    assert row["Status"] == "new_quote"


def test_dashboard_updates_exclude_protected_fields():
    row = build_dashboard_editor_rows([{
        "id": 9, "customer_name": "A", "quote_amount": 10, "quote_date": "2026-06-20",
        "follow_up_due_date": "2026-06-22", "status": "new_quote",
    }])[0]
    row.update({"Customer": "B", "Score": "999", "created_at": "changed", "response_token": "changed"})

    quote_id, updates = dashboard_quote_updates(row)

    assert quote_id == 9
    assert updates["customer_name"] == "B"
    assert "Score" not in updates
    assert "created_at" not in updates
    assert "response_token" not in updates
