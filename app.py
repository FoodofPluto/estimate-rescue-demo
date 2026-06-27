"""Streamlit app for Estimate Rescue."""

from __future__ import annotations

from datetime import date
import streamlit as st

import emailer
import storage
from config import get_settings
from dashboard_editor import build_dashboard_editor_rows, dashboard_quote_updates
from message_generator import (
    generate_ai_follow_up_message,
    generate_follow_up_message,
    render_saved_template,
    response_link_for_quote,
)
from quote_logic import (
    STATUSES,
    calculate_recovery_score,
    default_follow_up_due_date,
    format_currency,
    normalize_status,
    suggest_next_action,
)


st.set_page_config(page_title="Estimate Rescue", page_icon="ER", layout="wide")
storage.init_db()


def locked() -> bool:
    cfg = get_settings()
    if cfg.admin_password:
        return False
    st.warning("Operator area is locked. Set ADMIN_PASSWORD in `.env` or hosted secrets to enable login.")
    return True


def is_logged_in() -> bool:
    return bool(st.session_state.get("logged_in"))


def require_login() -> bool:
    if locked():
        return False
    if not is_logged_in():
        st.info("Please log in from the Operator Login page.")
        return False
    return True


def public_home() -> None:
    st.title("Estimate Rescue")
    st.subheader("Recover unsold quotes before they go cold.")
    st.write(
        "Estimate Rescue is a lightweight demo for local service businesses that send estimates "
        "and need a simple way to remember, follow up, and track what happened."
    )
    st.write(
        "This demo is configured for **Blue Ridge Auto Detail**, a fake local detailing shop "
        "that wants to recover missed ceramic coating, paint correction, interior cleaning, and fleet opportunities."
    )
    st.info("Use the sidebar to open Operator Login, then review the dashboard and follow-up queue.")
    st.caption("Local demo mode works without Resend or OpenAI keys. Operator pages require ADMIN_PASSWORD.")


def login_page() -> None:
    st.title("Operator Login")
    cfg = get_settings()
    if locked():
        return
    if is_logged_in():
        st.success("You are already logged in.")
        return
    with st.form("login_form"):
        password = st.text_input("Admin password", type="password")
        submitted = st.form_submit_button("Log in")
    if submitted:
        if password == cfg.admin_password:
            st.session_state["logged_in"] = True
            st.success("Logged in.")
            st.rerun()
        else:
            st.error("Incorrect password.")


def dashboard() -> None:
    if not require_login():
        return
    st.title("Operator Dashboard")
    st.caption("Today at a glance for Blue Ridge Auto Detail's unsold estimate follow-up workflow.")
    metrics = storage.dashboard_metrics()
    cols = st.columns(6)
    cols[0].metric("Open quotes", metrics["open_quotes"])
    cols[1].metric("Due today", metrics["follow_ups_due_today"])
    cols[2].metric("Overdue", metrics["overdue_quotes"])
    cols[3].metric("Open value", format_currency(metrics["open_quote_value"]))
    cols[4].metric("Won value", format_currency(metrics["won_quote_value"]))
    cols[5].metric("Lost value", format_currency(metrics["lost_quote_value"]))

    st.subheader("Highest recovery score opportunities")
    ranked = sorted(storage.list_dashboard_quotes(), key=calculate_recovery_score, reverse=True)[:5]
    if not ranked:
        st.info("No quotes yet.")
    else:
        rows = build_dashboard_editor_rows(ranked)
        edited = st.data_editor(
            rows,
            use_container_width=True,
            hide_index=True,
            disabled=["Score", "Next action"],
            column_config={
                "_quote_id": None,
                "Customer": st.column_config.TextColumn("Customer"),
                "Email": st.column_config.TextColumn("Email"),
                "Phone": st.column_config.TextColumn("Phone"),
                "Service": st.column_config.TextColumn("Service"),
                "Amount": st.column_config.NumberColumn("Amount", min_value=0.0, format="$%.2f"),
                "Due": st.column_config.TextColumn("Follow-up due (YYYY-MM-DD)"),
                "Status": st.column_config.SelectboxColumn("Status", options=list(STATUSES), required=True),
                "Source": st.column_config.TextColumn("Source"),
                "Score": st.column_config.TextColumn("Score", disabled=True),
                "Next action": st.column_config.TextColumn("Next action", disabled=True),
            },
            key="dashboard_quote_editor",
        )
        if st.button("Save dashboard edits", type="primary"):
            for row in edited:
                quote_id, updates = dashboard_quote_updates(row)
                storage.update_quote(quote_id, **updates)
            st.success("Dashboard edits saved.")
            st.rerun()

    st.subheader("Recent activity")
    if not metrics["recent_activity"]:
        st.info("No activity has been recorded yet.")
    for activity in metrics["recent_activity"]:
        st.caption(f"{activity['created_at']} - {activity['activity_summary']}")


def add_quote_page() -> None:
    if not require_login():
        return
    st.title("Add Quote")
    st.caption("Create a quote and assign the first follow-up date.")
    with st.form("add_quote"):
        customer_name = st.text_input("Customer name", "Alex Morgan")
        customer_email = st.text_input("Customer email", "alex@example.com")
        customer_phone = st.text_input("Customer phone")
        service_type = st.text_input("Service type", "Ceramic coating")
        quote_amount = st.number_input("Quote amount", min_value=0.0, value=595.0, step=25.0)
        quote_notes = st.text_area("Quote notes", "Customer asked about scheduling next week.")
        quote_date = st.date_input("Quote date", value=date.today())
        follow_up_due_date = st.date_input("Follow-up due date", value=date.fromisoformat(default_follow_up_due_date(quote_date)))
        source = st.text_input("Source", "website")
        submitted = st.form_submit_button("Create quote")
    if submitted:
        quote_id = storage.create_quote(
            customer_name,
            customer_email,
            customer_phone,
            service_type,
            quote_amount,
            quote_notes,
            quote_date.isoformat(),
            follow_up_due_date.isoformat(),
            "new_quote",
            source,
        )
        st.success(f"Quote #{quote_id} created.")
        st.info("Open Quote Detail to generate a follow-up message or copy the customer's response link.")


def follow_up_queue() -> None:
    if not require_login():
        return
    st.title("Follow-Up Queue")
    st.caption("Due and overdue quotes that need operator attention.")
    queue = storage.list_follow_up_queue()
    if not queue:
        st.success("No due or overdue follow-ups.")
        return
    rows = []
    for q in queue:
        rows.append(
            {
                "ID": q["id"],
                "Customer": q["customer_name"],
                "Service": q["service_type"],
                "Amount": format_currency(q["quote_amount"]),
                "Due": q["follow_up_due_date"],
                "Status": STATUSES[normalize_status(q["status"])],
                "Score": calculate_recovery_score(q),
                "Next action": suggest_next_action(q),
            }
        )
    st.dataframe(rows, use_container_width=True, hide_index=True)
    selected = st.selectbox("Open quote", [q["id"] for q in queue], format_func=lambda qid: f"Quote #{qid}")
    if st.button("Open selected quote"):
        st.session_state["selected_quote_id"] = selected
        st.session_state["page"] = "Quote Detail"
        st.rerun()


def quote_detail() -> None:
    if not require_login():
        return
    st.title("Quote Detail")
    quote_ids = [q["id"] for q in storage.list_quotes()]
    if not quote_ids:
        st.info("No quotes yet.")
        return
    default_id = st.session_state.get("selected_quote_id", quote_ids[0])
    quote_id = st.selectbox("Quote", quote_ids, index=quote_ids.index(default_id) if default_id in quote_ids else 0)
    quote = storage.get_quote(int(quote_id))
    if not quote:
        st.error("Quote not found.")
        return

    customer_title = str(quote.get("customer_name") or "").strip() or "Unnamed Customer"
    st.subheader(customer_title)
    st.caption(f"Created {quote.get('created_at') or 'Unknown date'} · {quote['service_type']}")
    cols = st.columns(4)
    cols[0].metric("Amount", format_currency(quote["quote_amount"]))
    cols[1].metric("Status", STATUSES[normalize_status(quote["status"])])
    cols[2].metric("Follow-up due", quote["follow_up_due_date"])
    cols[3].metric("Recovery score", calculate_recovery_score(quote))
    st.write(suggest_next_action(quote))
    token = storage.ensure_quote_response_token(quote["id"])
    quote["public_response_token"] = token
    response_url = response_link_for_quote(quote)
    st.caption(f"Response token: {token}")
    if response_url:
        st.code(response_url, language="text")

    st.subheader("Generate follow-up")
    tone = st.selectbox("Tone", ["friendly", "professional", "casual", "urgent", "premium"])
    settings = storage.get_business_settings()
    generated = generate_follow_up_message(quote, settings, tone=tone)
    templates = storage.list_message_templates()
    if templates:
        selected_template = st.selectbox(
            "Saved template",
            ["Use deterministic default"] + [t["template_key"] for t in templates],
        )
        if selected_template != "Use deterministic default":
            template = next(t for t in templates if t["template_key"] == selected_template)
            generated = render_saved_template(template, quote, settings)
    if st.button("Try optional OpenAI version"):
        ai_message = generate_ai_follow_up_message(quote, settings, tone=tone)
        if ai_message:
            generated = ai_message
            st.success("Generated with OpenAI.")
        else:
            st.info("OpenAI is not configured or generation failed; using deterministic message.")

    with st.form(f"send_follow_up_{quote_id}"):
        subject = st.text_input("Subject", generated["subject"])
        body = st.text_area("Body", generated["body"], height=240)
        send = st.form_submit_button("Send / record follow-up")
    if send:
        result = emailer.send_email(
            to_email=quote["customer_email"],
            subject=subject,
            body=body,
            from_email=settings.get("default_from_email") or None,
            reply_to=settings.get("owner_email"),
        )
        storage.create_follow_up(
            quote["id"],
            "email",
            subject,
            body,
            quote["customer_email"],
            result["status"],
            storage.now_iso() if result["status"] == "sent" else None,
        )
        if result["status"] == "sent":
            storage.update_quote(quote["id"], status="follow_up_sent")
            st.success("Email sent and follow-up recorded.")
        else:
            st.warning(result["message"])
            st.info("The follow-up was still saved so the demo history stays complete.")

    st.subheader("Manual status")
    status = st.selectbox("Status", list(STATUSES), index=list(STATUSES).index(normalize_status(quote["status"])))
    if st.button("Update status"):
        storage.update_quote(quote["id"], status=status)
        storage.add_activity(quote["id"], "status_updated", f"Status changed to {STATUSES[status]}.")
        st.success("Status updated.")
        st.rerun()

    st.subheader("Follow-up history")
    st.dataframe(storage.list_follow_ups_for_quote(quote["id"]), use_container_width=True, hide_index=True)
    st.subheader("Customer responses")
    st.dataframe(storage.list_customer_responses_for_quote(quote["id"]), use_container_width=True, hide_index=True)


def customer_response_page() -> None:
    st.title("Customer Response")
    token = st.query_params.get("token", "")
    if not token:
        st.error("This response link is missing a token.")
        return
    quote = storage.get_quote_by_token(token)
    if not quote:
        st.error("This response link is invalid or expired.")
        return
    settings = storage.get_business_settings()
    st.write(f"Hi {quote['customer_name']}, thanks for reviewing your estimate from {settings['business_name']}.")
    st.write(f"**{quote['service_type']}** - {format_currency(quote['quote_amount'])}")
    st.caption("Choose the option that best fits where you are. A short note is optional.")
    notes = st.text_area("Optional note")
    options = [
        ("I want to book", "book"),
        ("I have a question", "question"),
        ("I am still deciding", "deciding"),
        ("Not interested anymore", "not_interested"),
    ]
    for label, response_type in options:
        if st.button(label):
            storage.create_customer_response(quote["id"], response_type, notes)
            st.success("Thanks, your response has been recorded.")


def settings_page() -> None:
    if not require_login():
        return
    st.title("Settings / Message Templates")
    st.info(
        "Business settings supply the sender/reply-to details and template variables used by Quote Detail. "
        "Saved templates affect a follow-up draft only when the operator selects that template in Quote Detail. "
        "They do not change the public customer response page, optional AI drafts, or create automatic reminders."
    )
    settings = storage.get_business_settings()
    with st.form("business_settings"):
        business_name = st.text_input("Business name", settings["business_name"])
        owner_email = st.text_input("Owner email", settings["owner_email"])
        default_from_email = st.text_input("Default from email", settings["default_from_email"])
        service_category = st.text_input("Service category", settings["service_category"])
        brand_voice = st.text_area("Brand voice", settings["brand_voice"])
        if st.form_submit_button("Save settings"):
            storage.upsert_business_settings(business_name, owner_email, default_from_email, service_category, brand_voice)
            st.success("Settings saved.")

    st.subheader("Templates")
    st.caption("Use: operator-generated email drafts in Quote Detail. Saving a template does not send anything.")
    st.caption("Variables: $customer_name, $business_name, $service_type, $quote_amount, $response_link")
    templates = storage.list_message_templates()
    selected_key = st.selectbox("Template", [t["template_key"] for t in templates] or ["first_follow_up"])
    existing = next((t for t in templates if t["template_key"] == selected_key), {})
    with st.form("template_form"):
        template_key = st.text_input("Template key", existing.get("template_key", selected_key))
        template_name = st.text_input("Template name", existing.get("template_name", "First Follow-Up"))
        subject_template = st.text_input("Subject template", existing.get("subject_template", "Following up on your $service_type estimate"))
        body_template = st.text_area("Body template", existing.get("body_template", "Hi $customer_name,\n\nChecking in from $business_name."))
        if st.form_submit_button("Save template"):
            storage.upsert_message_template(template_key, template_name, subject_template, body_template)
            st.success("Template saved.")

    if templates:
        sample = {
            "customer_name": "Maya",
            "business_name": settings["business_name"],
            "service_type": "Ceramic coating",
            "quote_amount": "$1,295.00",
            "response_link": "https://example.com/respond",
        }
        st.subheader("Selected template preview")
        st.write(render_saved_template(existing, sample, settings)["subject"])
        st.text(render_saved_template(existing, sample, settings)["body"])


PAGES = {
    "Public Demo Home": public_home,
    "Operator Login": login_page,
    "Operator Dashboard": dashboard,
    "Add Quote": add_quote_page,
    "Follow-Up Queue": follow_up_queue,
    "Quote Detail": quote_detail,
    "Customer Response Page": customer_response_page,
    "Settings / Message Templates": settings_page,
}


def main() -> None:
    if is_logged_in() and st.sidebar.button("Logout"):
        st.session_state["logged_in"] = False
        st.session_state.pop("selected_quote_id", None)
        st.success("Logged out.")
    query_page = st.query_params.get("page")
    if query_page in PAGES:
        st.session_state["page"] = query_page
    current_page = st.session_state.get("page", "Public Demo Home")
    page = st.sidebar.radio("Navigation", list(PAGES), index=list(PAGES).index(current_page))
    if page != current_page:
        st.session_state["page"] = page
        st.rerun()
    PAGES[page]()


if __name__ == "__main__":
    main()
