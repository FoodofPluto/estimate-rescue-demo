from datetime import UTC, date, datetime, timedelta
import importlib
import os
from types import SimpleNamespace

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
    lead = storage.get_lead(lead_id)
    assert lead["status"] == "New"
    assert lead["public_response_token"]
    assert "acknowledgment" in {event["event_type"] for event in storage.list_lead_events(lead_id)}
    assert storage.list_lead_messages(lead_id)[0]["status"] == "simulated"


def test_existing_lead_without_token_is_lazily_assigned_stable_token(tmp_path):
    storage = load_storage(tmp_path)
    lead_id = make_lead(storage)
    with storage.get_connection() as conn:
        conn.execute("UPDATE leads SET public_response_token=NULL WHERE id=?", (lead_id,))

    first_token = storage.ensure_lead_response_token(lead_id)
    second_token = storage.ensure_lead_response_token(lead_id)

    assert first_token
    assert second_token == first_token
    assert storage.get_lead_by_token(first_token)["id"] == lead_id


def test_init_db_backfills_legacy_tokenless_leads(tmp_path):
    storage = load_storage(tmp_path)
    lead_id = make_lead(storage)
    with storage.get_connection() as conn:
        conn.execute("UPDATE leads SET public_response_token='' WHERE id=?", (lead_id,))
    storage.init_db()
    assert storage.get_lead(lead_id)["public_response_token"]


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


def test_lead_customer_response_updates_only_intended_lead(tmp_path):
    storage = load_storage(tmp_path)
    lead_id = make_lead(storage, status="Estimate Sent")
    other_id = make_lead(storage, customer_name="Other Homeowner", email="other@example.com", status="Estimate Sent")

    storage.create_lead_customer_response(lead_id, "need_more_time", "Call next month.")

    assert storage.get_lead(lead_id)["status"] == "Not Ready"
    assert storage.get_lead(other_id)["status"] == "Estimate Sent"
    events = storage.list_lead_events(lead_id)
    assert any(event["event_type"] == "customer_response" for event in events)


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
    assert app.safe_page_name("Operator Dashboard") == "Follow-Up Dashboard"


def test_sales_intro_and_demo_status_text_are_sales_ready(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "copy.db"))
    import app

    intro = " ".join(app.dashboard_intro_text())
    demo_status = " ".join(app.demo_status_text())

    assert "LeadLoop Ops" in intro
    assert "Estimate Rescue" in intro
    assert "contractors" in intro
    assert "paid pilot" in app.PAID_PILOT_CTA
    assert "Follow-up messages are simulated" in demo_status
    assert "Public response links are demo links" in demo_status
    assert "No real SMS, email, CRM, or payment actions" in demo_status


def test_dashboard_action_labels_are_contractor_friendly(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "labels.db"))
    import app

    assert app.DASHBOARD_ACTION_LABELS == {
        "view": "View/Edit Lead",
        "followed_up": "Mark Followed Up",
        "booked": "Mark Booked",
        "lost": "Mark Lost",
        "pause": "Pause Follow-Up",
        "schedule": "Schedule Follow-Up",
        "open_response": "Open Response Link",
    }


def test_empty_state_helpers_tell_operator_how_to_populate_demo(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "empty-state.db"))
    import app

    messages = []
    fake_streamlit = SimpleNamespace(
        info=lambda message: messages.append(message),
        success=lambda message: messages.append(message),
        markdown=lambda message: messages.append(message),
    )
    monkeypatch.setattr(app, "st", fake_streamlit)

    app.render_no_leads_state("detail")
    app.render_no_follow_ups_state()

    combined = " ".join(messages)
    assert "Submit a demo lead" in combined
    assert "Demo Controls" in combined
    assert "Lead Detail will show customer info" in combined
    assert "Leads with open estimates" in combined


def test_single_click_navigation_updates_page_and_reruns(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "navigation-rerun.db"))
    import app

    reruns = []
    fake_streamlit = SimpleNamespace(session_state={"page": "Customer Estimate Request"}, rerun=lambda: reruns.append("rerun"))
    monkeypatch.setattr(app, "st", fake_streamlit)

    changed = app.apply_page_selection("Lead Detail", "Customer Estimate Request")

    assert changed is True
    assert fake_streamlit.session_state["page"] == "Lead Detail"
    assert fake_streamlit.session_state["nav_page"] == "Lead Detail"
    assert reruns == ["rerun"]


def test_same_page_navigation_does_not_rerun(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "navigation-same.db"))
    import app

    reruns = []
    fake_streamlit = SimpleNamespace(session_state={"page": "Lead Detail"}, rerun=lambda: reruns.append("rerun"))
    monkeypatch.setattr(app, "st", fake_streamlit)

    changed = app.apply_page_selection("Lead Detail", "Lead Detail")

    assert changed is False
    assert reruns == []


def test_dashboard_status_action_updates_correct_lead(tmp_path, monkeypatch):
    storage = load_storage(tmp_path)
    lead_id = make_lead(storage)
    other_id = make_lead(storage, customer_name="Other Homeowner", email="other@example.com")
    import app

    reruns = []
    fake_streamlit = SimpleNamespace(success=lambda message: None, rerun=lambda: reruns.append("rerun"))
    monkeypatch.setattr(app, "storage", storage)
    monkeypatch.setattr(app, "st", fake_streamlit)

    app.update_lead_status(lead_id, "Booked")

    assert storage.get_lead(lead_id)["status"] == "Booked"
    assert storage.get_lead(other_id)["status"] == "New"
    assert reruns == ["rerun"]


def test_dashboard_view_action_routes_to_lead_detail(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "route.db"))
    import app

    reruns = []
    fake_streamlit = SimpleNamespace(session_state={}, rerun=lambda: reruns.append("rerun"))
    monkeypatch.setattr(app, "st", fake_streamlit)

    app.route_to_lead_detail(42)

    assert fake_streamlit.session_state["selected_lead_id"] == 42
    assert fake_streamlit.session_state["page"] == "Lead Detail"
    assert fake_streamlit.session_state["nav_page"] == "Lead Detail"
    assert reruns == ["rerun"]


def test_lead_action_context_includes_customer_contact_and_activity(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "action-context.db"))
    import app

    context = app.lead_action_context(
        {
            "customer_name": "Casey Martin",
            "email": "casey@example.com",
            "phone": "555-0188",
            "booked_value_estimate": 4200,
            "status": "Estimate Sent",
            "next_follow_up_at": "2026-07-09T00:00:00+00:00",
        },
        "https://demo.example/?customer_response_token=abc",
        [{"event_type": "customer_response", "timestamp": "2026-07-07T12:00:00+00:00", "message": "Customer response: need more time."}],
        [{"template_name": "estimate_follow_up", "sent_at": "2026-07-06T12:00:00+00:00"}],
    )

    assert context["Customer"] == "Casey Martin"
    assert context["Email"] == "casey@example.com"
    assert context["Phone"] == "555-0188"
    assert context["Estimate amount"] == "$4,200"
    assert context["Current status"] == "Estimate Sent"
    assert context["Last follow-up"] == "2026-07-06T12:00:00+00:00"
    assert "need more time" in context["Most recent customer response or activity"]
    assert context["Public response link"].endswith("abc")


def test_lead_detail_sections_preserve_key_fields(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "detail-sections.db"))
    import app

    sections = app.lead_detail_sections(
        {
            "customer_name": "Jordan Smith",
            "email": "jordan@example.com",
            "phone": "555-0199",
            "preferred_contact_method": "Text",
            "source": "Website",
            "booked_value_estimate": 9800,
            "service_type": "Heat pump replacement",
            "status": "Follow-Up Due",
            "urgency": "Soon",
            "assigned_to": "Office",
            "description": "Customer wants a replacement estimate.",
            "next_follow_up_at": "2026-07-10T00:00:00+00:00",
        },
        "https://demo.example/?customer_response_token=def",
    )

    assert sections["header"]["Customer"] == "Jordan Smith"
    assert sections["header"]["Status"] == "Follow-Up Due"
    assert sections["contact"]["Email"] == "jordan@example.com"
    assert sections["contact"]["Phone"] == "555-0199"
    assert sections["opportunity"]["Service type"] == "Heat pump replacement"
    assert sections["opportunity"]["Notes"] == "Customer wants a replacement estimate."
    assert sections["follow_up"]["Next follow-up"] == "2026-07-10T00:00:00+00:00"
    assert sections["follow_up"]["Public response link"].endswith("def")


def test_public_customer_response_token_bypasses_operator_navigation(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "public-route.db"))
    import app

    called = []
    fake_streamlit = SimpleNamespace(query_params={"customer_response_token": "abc"}, sidebar=SimpleNamespace(title=lambda *_: (_ for _ in ()).throw(AssertionError("sidebar should not render"))))
    monkeypatch.setattr(app, "st", fake_streamlit)
    monkeypatch.setattr(app, "public_customer_response", lambda: called.append("public"))

    app.main()

    assert called == ["public"]


def test_lead_customer_response_token_routes_to_lead_page(tmp_path, monkeypatch):
    storage = load_storage(tmp_path)
    lead_id = make_lead(storage)
    token = storage.get_lead(lead_id)["public_response_token"]
    import app

    rendered = []
    fake_streamlit = SimpleNamespace(query_params={"customer_response_token": token})
    monkeypatch.setattr(app, "storage", storage)
    monkeypatch.setattr(app, "st", fake_streamlit)
    monkeypatch.setattr(app, "render_lead_customer_response", lambda lead: rendered.append(("lead", lead["id"])))
    monkeypatch.setattr(app, "render_quote_customer_response", lambda quote: rendered.append(("quote", quote["id"])))

    app.public_customer_response()

    assert rendered == [("lead", lead_id)]


def test_quote_customer_response_token_still_routes_to_quote_page(tmp_path, monkeypatch):
    storage = load_storage(tmp_path)
    quote_id = storage.create_quote("Quote Customer", "quote@example.com", "", "AC quote", 500, "", "2026-01-01")
    token = storage.get_quote(quote_id)["public_response_token"]
    import app

    rendered = []
    fake_streamlit = SimpleNamespace(query_params={"customer_response_token": token})
    monkeypatch.setattr(app, "storage", storage)
    monkeypatch.setattr(app, "st", fake_streamlit)
    monkeypatch.setattr(app, "render_lead_customer_response", lambda lead: rendered.append(("lead", lead["id"])))
    monkeypatch.setattr(app, "render_quote_customer_response", lambda quote: rendered.append(("quote", quote["id"])))

    app.public_customer_response()

    assert rendered == [("quote", quote_id)]


def test_invalid_customer_response_token_is_safe(tmp_path, monkeypatch):
    load_storage(tmp_path)
    import app

    messages = []
    fake_streamlit = SimpleNamespace(
        query_params={"customer_response_token": "missing"},
        caption=lambda message: messages.append(("caption", message)),
        title=lambda message: messages.append(("title", message)),
        error=lambda message: messages.append(("error", message)),
    )
    monkeypatch.setattr(app, "st", fake_streamlit)

    app.public_customer_response()

    assert ("error", "This response link is invalid or has expired.") in messages


def test_lead_response_link_uses_stable_token(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_BASE_URL", "https://demo.example")
    storage = load_storage(tmp_path)
    lead_id = make_lead(storage)
    lead = storage.get_lead(lead_id)
    import config
    import message_generator
    import app

    importlib.reload(config)
    importlib.reload(message_generator)
    monkeypatch.setattr(app, "storage", storage)
    monkeypatch.setattr(app, "message_generator", message_generator)

    link = app.lead_response_link(lead)

    assert link == f"https://demo.example?customer_response_token={lead['public_response_token']}"
