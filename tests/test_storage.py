import importlib
import os


def load_storage(tmp_path):
    os.environ["DATABASE_PATH"] = str(tmp_path / "test.db")
    import storage

    importlib.reload(storage)
    storage.init_db()
    return storage


def test_init_db_creates_tables(tmp_path):
    storage = load_storage(tmp_path)
    with storage.get_connection() as conn:
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
    assert "quotes" in tables
    assert "follow_ups" in tables
    assert "business_settings" in tables


def test_create_and_get_quote(tmp_path):
    storage = load_storage(tmp_path)
    quote_id = storage.create_quote(
        "Test Customer",
        "test@example.com",
        "",
        "Interior detail",
        250,
        "Needs seats cleaned.",
        "2026-01-01",
    )
    quote = storage.get_quote(quote_id)
    assert quote["customer_name"] == "Test Customer"
    assert quote["public_response_token"]


def test_tokenless_quote_is_backfilled_once_and_resolves(tmp_path):
    storage = load_storage(tmp_path)
    quote_id = storage.create_quote(
        "Legacy Customer", "legacy@example.com", "", "Detail", 200, "", "2026-01-01"
    )
    with storage.get_connection() as conn:
        conn.execute("UPDATE quotes SET public_response_token=NULL WHERE id=?", (quote_id,))

    first_token = storage.ensure_quote_response_token(quote_id)
    second_token = storage.ensure_quote_response_token(quote_id)

    assert first_token
    assert second_token == first_token
    assert storage.get_quote_by_token(first_token)["id"] == quote_id


def test_init_db_backfills_legacy_tokenless_quotes(tmp_path):
    storage = load_storage(tmp_path)
    quote_id = storage.create_quote(
        "Legacy Customer", "legacy@example.com", "", "Detail", 200, "", "2026-01-01"
    )
    with storage.get_connection() as conn:
        conn.execute("UPDATE quotes SET public_response_token='' WHERE id=?", (quote_id,))
    storage.init_db()
    assert storage.get_quote(quote_id)["public_response_token"]


def test_dashboard_metrics_and_follow_up_queue(tmp_path):
    storage = load_storage(tmp_path)
    storage.create_quote(
        "Due Customer",
        "due@example.com",
        "",
        "Paint correction",
        900,
        "",
        "2026-01-01",
        "2026-01-02",
    )
    storage.create_quote(
        "Won Customer",
        "won@example.com",
        "",
        "Maintenance",
        100,
        "",
        "2026-01-01",
        "2026-01-02",
        "won",
    )
    metrics = storage.dashboard_metrics()
    queue = storage.list_follow_up_queue()
    assert metrics["open_quotes"] == 1
    assert metrics["won_quote_value"] == 100
    assert len(queue) == 1


def test_fresh_dashboard_is_empty_and_explicit_demo_rows_are_hidden(tmp_path):
    storage = load_storage(tmp_path)
    assert storage.list_dashboard_quotes() == []
    assert storage.dashboard_metrics()["open_quotes"] == 0
    storage.create_quote(
        "Seed Customer", "seed@example.com", "", "Detail", 100, "", "2026-01-01", source="demo seed"
    )
    assert storage.list_dashboard_quotes() == []
    assert storage.dashboard_metrics()["recent_activity"] == []


def test_update_quote_does_not_modify_system_fields(tmp_path):
    storage = load_storage(tmp_path)
    quote_id = storage.create_quote(
        "Customer", "customer@example.com", "", "Detail", 100, "", "2026-01-01"
    )
    before = storage.get_quote(quote_id)
    storage.update_quote(
        quote_id,
        customer_name="Edited Customer",
        public_response_token="unsafe-replacement",
        created_at="unsafe-date",
        id=999,
    )
    after = storage.get_quote(quote_id)
    assert after["customer_name"] == "Edited Customer"
    assert after["public_response_token"] == before["public_response_token"]
    assert after["created_at"] == before["created_at"]


def test_customer_response_updates_status_and_activity(tmp_path):
    storage = load_storage(tmp_path)
    quote_id = storage.create_quote(
        "Question Customer",
        "question@example.com",
        "",
        "Ceramic coating",
        1200,
        "",
        "2026-01-01",
        "2026-01-02",
    )
    storage.create_customer_response(quote_id, "question", "Can I drop off Friday?")
    quote = storage.get_quote(quote_id)
    responses = storage.list_customer_responses_for_quote(quote_id)
    metrics = storage.dashboard_metrics()
    assert storage.status_for_customer_response("not_interested") == "lost"
    assert quote["status"] == "customer_question"
    assert responses[0]["response_notes"] == "Can I drop off Friday?"
    assert any("Customer response" in item["activity_summary"] for item in metrics["recent_activity"])


def test_invalid_customer_response_token_returns_none(tmp_path):
    storage = load_storage(tmp_path)
    assert storage.get_quote_by_token("") is None
    assert storage.get_quote_by_token("missing-token") is None


def test_disabled_email_follow_up_can_be_recorded(tmp_path, monkeypatch):
    storage = load_storage(tmp_path)
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.delenv("RESEND_FROM_EMAIL", raising=False)
    import emailer

    quote_id = storage.create_quote(
        "Email Customer",
        "email@example.com",
        "",
        "Paint correction",
        800,
        "",
        "2026-01-01",
        "2026-01-02",
    )
    result = emailer.send_email(to_email="email@example.com", subject="Hi", body="Body")
    storage.create_follow_up(quote_id, "email", "Hi", "Body", "email@example.com", result["status"])
    follow_ups = storage.list_follow_ups_for_quote(quote_id)
    assert result["status"] == "email_disabled"
    assert follow_ups[0]["delivery_status"] == "email_disabled"


def test_seed_demo_data_if_empty_is_idempotent(tmp_path):
    storage = load_storage(tmp_path)
    storage.seed_demo_data_if_empty()
    first_count = len(storage.list_leads())
    storage.seed_demo_data_if_empty()
    second_count = len(storage.list_leads())
    assert first_count == 8
    assert second_count == 8


def test_dashboard_metrics_after_status_change(tmp_path):
    storage = load_storage(tmp_path)
    quote_id = storage.create_quote(
        "Status Customer",
        "status@example.com",
        "",
        "Fleet wash",
        1500,
        "",
        "2026-01-01",
        "2026-01-02",
    )
    assert storage.dashboard_metrics()["open_quote_value"] == 1500
    storage.update_quote(quote_id, status="won")
    metrics = storage.dashboard_metrics()
    assert metrics["open_quotes"] == 0
    assert metrics["won_quote_value"] == 1500
