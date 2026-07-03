from datetime import UTC, date, datetime, timedelta
import importlib
import os

from leadloop_logic import follow_up_action


def load_storage(tmp_path):
    os.environ["DATABASE_PATH"] = str(tmp_path / "leadloop.db")
    import storage
    importlib.reload(storage)
    storage.init_db()
    return storage


def make_lead(storage, **overrides):
    values = dict(customer_name="Test Homeowner", email="home@example.com", phone="555-0100",
        service_type="AC repair", urgency="Soon", preferred_contact_method="Email",
        description="System is not cooling.")
    values.update(overrides)
    return storage.create_lead(**values)


def test_submission_creates_lead_acknowledgment_and_simulated_message(tmp_path):
    storage = load_storage(tmp_path)
    lead_id = make_lead(storage)
    assert storage.get_lead(lead_id)["status"] == "New"
    assert "acknowledgment" in {event["event_type"] for event in storage.list_lead_events(lead_id)}
    assert storage.list_lead_messages(lead_id)[0]["status"] == "simulated"


def test_follow_up_stages_and_terminal_exclusions(tmp_path):
    storage = load_storage(tmp_path)
    old = (datetime.now(UTC) - timedelta(days=6)).isoformat()
    due_id = make_lead(storage, status="Estimate Sent", created_at=old)
    assert follow_up_action(storage.get_lead(due_id), date.today()) == "Follow-up 2 due"
    for status in ("Booked", "Lost", "Paused"):
        make_lead(storage, status=status, created_at=old)
    storage.update_lead(due_id, paused=1)
    assert storage.list_follow_up_leads() == []


def test_status_update_and_seed_are_idempotent(tmp_path):
    storage = load_storage(tmp_path)
    lead_id = make_lead(storage)
    storage.update_lead(lead_id, status="Booked")
    assert storage.get_lead(lead_id)["status"] == "Booked"
    storage.reset_leadloop_demo_data()
    from seed_data import seed_demo_data
    seed_demo_data(); seed_demo_data()
    assert len(storage.list_leads()) == 8


def test_follow_up_completion_clears_current_due_action(tmp_path):
    storage = load_storage(tmp_path)
    old = (datetime.now(UTC) - timedelta(days=6)).isoformat()
    lead_id = make_lead(storage, status="Estimate Sent", created_at=old)
    assert follow_up_action(storage.get_lead(lead_id)) == "Follow-up 2 due"
    storage.create_simulated_follow_up(lead_id, "Checking in")
    assert follow_up_action(storage.get_lead(lead_id)) is None
    assert storage.list_lead_messages(lead_id)[0]["status"] == "simulated"


def test_opt_out_is_excluded(tmp_path):
    storage = load_storage(tmp_path)
    lead_id = make_lead(storage)
    with storage.get_connection() as conn:
        conn.execute("UPDATE leads SET opted_out=1 WHERE id=?", (lead_id,))
    assert follow_up_action(storage.get_lead(lead_id)) is None


def test_assignment_edit_does_not_reset_follow_up_clock(tmp_path):
    storage = load_storage(tmp_path)
    old = (datetime.now(UTC) - timedelta(days=3)).isoformat()
    lead_id = make_lead(storage, status="Estimate Sent", created_at=old)
    before = storage.get_lead(lead_id)["status_changed_at"]
    storage.update_lead(lead_id, status="Estimate Sent", assigned_to="Jamie")
    after = storage.get_lead(lead_id)
    assert after["status_changed_at"] == before
    assert follow_up_action(after) == "No reply after 2 days"


def test_stale_navigation_value_is_safe(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "navigation.db"))
    import app
    assert app.safe_page_name("Removed Page") == "Customer Estimate Request"
