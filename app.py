"""LeadLoop Ops: lead response and estimate follow-up demo."""

from __future__ import annotations

from datetime import UTC, date, datetime, time

import streamlit as st

import message_generator
import storage
from config import get_settings
from leadloop_logic import STATUSES, follow_up_action
from seed_data import seed_demo_data

COMPANY = "Blue Ridge Comfort Pros"
POSITIONING = "LeadLoop Ops helps small home-service companies respond to every web lead quickly and follow up every open estimate so fewer jobs fall through the cracks."
WORKFLOW_EXPLANATION = [
    "Customer submits a lead through the intake form.",
    "The lead becomes an estimate/opportunity for the operator to work.",
    "The operator uses Lead Detail to edit status, estimate information, and follow-up details.",
    "The Follow-Up Dashboard shows what needs attention and supports quick updates.",
    "Customer response links simulate how customers can re-engage with an estimate.",
    "Demo mode uses simulated data and messages; no real email or SMS is sent.",
]
SALES_INTRO = [
    "LeadLoop Ops keeps home-service leads and open estimates from getting lost after the first call.",
    "Estimate Rescue is the follow-up workflow inside LeadLoop Ops. It shows which estimates need attention, lets the office update each lead, and gives customers a simple demo response link.",
    "This demo is built for contractors and small office teams that need a clear daily list of who to follow up with next.",
    "Start by reviewing the Follow-Up Dashboard, then open Lead Detail to update the customer, estimate status, next follow-up date, and response link.",
]
DEMO_STATUS = [
    "Customer data is simulated unless you submit a demo lead through the intake form.",
    "Follow-up messages are simulated and recorded in the activity history.",
    "Public response links are demo links for showing how customers can re-engage.",
    "No real SMS, email, CRM, or payment actions are sent from this demo unless explicitly configured.",
    "This is a working demo intended for paid pilot discussions.",
]
PAID_PILOT_CTA = "Want this adapted to your real follow-up process? This demo can be used as the starting point for a paid pilot."
DASHBOARD_ACTION_LABELS = {
    "view": "View/Edit Lead",
    "followed_up": "Mark Followed Up",
    "booked": "Mark Booked",
    "lost": "Mark Lost",
    "pause": "Pause Follow-Up",
    "schedule": "Schedule Follow-Up",
    "open_response": "Open Response Link",
}

st.set_page_config(page_title="LeadLoop Ops", layout="wide")
storage.init_db()


def demo_header() -> None:
    st.caption("DEMO MODE - No real email or SMS is sent")


def how_it_works() -> None:
    with st.expander("How LeadLoop Ops Works", expanded=True):
        for item in WORKFLOW_EXPLANATION:
            st.markdown(f"- {item}")
        st.caption("Estimate Rescue is the estimate follow-up workflow inside LeadLoop Ops.")


def dashboard_intro_text() -> list[str]:
    return SALES_INTRO


def demo_status_text() -> list[str]:
    return DEMO_STATUS


def render_sales_intro() -> None:
    st.subheader("LeadLoop Ops and Estimate Rescue")
    for paragraph in dashboard_intro_text():
        st.write(paragraph)
    st.info(PAID_PILOT_CTA)


def render_demo_status() -> None:
    with st.expander("Demo Status - What is simulated?", expanded=True):
        for item in demo_status_text():
            st.markdown(f"- {item}")


def render_no_leads_state(context: str = "dashboard") -> None:
    st.info("No leads match this view yet.")
    st.markdown("- Submit a demo lead through Customer Estimate Request to see it become an opportunity.")
    st.markdown("- Use Demo Controls to seed or reset fictional HVAC leads for the sales walkthrough.")
    st.markdown("- Once leads exist, this area will show who needs attention, current status, next follow-up, and response links.")
    if context == "detail":
        st.markdown("- After a lead exists, Lead Detail will show customer info, estimate status, follow-up timing, the public response link, and activity history.")


def render_no_follow_ups_state() -> None:
    st.success("No follow-ups are due right now.")
    st.markdown("- Submit a demo lead or seed demo data to populate Estimate Rescue.")
    st.markdown("- Leads with open estimates, no reply, or follow-up dates due will appear here.")
    st.markdown("- Booked, lost, paused, and opted-out leads stay out of this queue.")


def locked() -> bool:
    if get_settings().admin_password:
        return False
    st.warning("Operator area is locked. Set ADMIN_PASSWORD to enable operator access.")
    return True


def require_login() -> bool:
    if locked():
        return False
    if not st.session_state.get("logged_in"):
        st.info("Log in from Operator Login to view company lead data.")
        return False
    return True


def request_form() -> None:
    demo_header()
    st.title(f"Request service from {COMPANY}")
    st.write("Tell us what is happening. This creates a LeadLoop Ops lead and estimate opportunity for the office team.")
    with st.form("estimate_request", clear_on_submit=True):
        left, right = st.columns(2)
        name = left.text_input("Name *")
        email = right.text_input("Email *")
        phone = left.text_input("Phone *")
        service = right.selectbox("Service type", ["AC repair", "Heating repair", "Heat pump replacement", "Seasonal maintenance", "Mini-split quote", "Thermostat service", "Other"])
        urgency = left.selectbox("Urgency", ["Routine", "Soon", "Urgent - no heating or cooling"])
        contact = right.selectbox("Preferred contact method", ["Email", "Phone", "Text"])
        description = st.text_area("Describe the problem or project *")
        consent = st.checkbox("I agree that Blue Ridge Comfort Pros may contact me about this request.")
        submitted = st.form_submit_button("Send request", type="primary")
    if submitted:
        if not all([name.strip(), email.strip(), phone.strip(), description.strip(), consent]):
            st.error("Complete the required fields and communication acknowledgment.")
            return
        lead_id = storage.create_lead(
            customer_name=name,
            email=email,
            phone=phone,
            service_type=service,
            urgency=urgency,
            preferred_contact_method=contact,
            description=description,
        )
        st.success(f"Request received. Your reference is LL-{lead_id:04d}.")
        st.info(f"A {contact.lower()} acknowledgment was simulated and the {COMPANY} office was alerted.")


def login_page() -> None:
    demo_header()
    st.title("Operator Login")
    if locked() or st.session_state.get("logged_in"):
        if st.session_state.get("logged_in"):
            st.success("Logged in.")
        return
    with st.form("login"):
        password = st.text_input("Admin password", type="password")
        submitted = st.form_submit_button("Log in")
    if submitted:
        if password == get_settings().admin_password:
            st.session_state["logged_in"] = True
            st.rerun()
        st.error("Incorrect password.")


def age_label(created_at: str) -> str:
    created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    days = max((datetime.now(UTC) - created).days, 0)
    return "Today" if days == 0 else f"{days} day{'s' if days != 1 else ''}"


def next_follow_up_date_value(lead: dict[str, object]) -> date:
    raw = str(lead.get("next_follow_up_at") or "")
    if raw:
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
        except ValueError:
            pass
    return datetime.now(UTC).date()


def route_to_lead_detail(lead_id: int) -> None:
    st.session_state["selected_lead_id"] = lead_id
    st.session_state["page"] = "Lead Detail"
    st.rerun()


def update_lead_status(lead_id: int, status: str) -> None:
    storage.update_lead(lead_id, status=status, outcome=status if status in {"Booked", "Lost", "Not Ready"} else None)
    st.success(f"Lead marked {status.lower()}.")
    st.rerun()


def mark_followed_up(lead_id: int) -> None:
    lead = storage.get_lead(lead_id)
    if not lead:
        st.error("Lead was not found.")
        return
    preview = f"Operator completed a demo follow-up with {lead['customer_name']} about {lead['service_type']}."
    storage.create_simulated_follow_up(lead_id, preview, str(lead["preferred_contact_method"] or "email").lower())
    st.success("Follow-up recorded as simulated.")
    st.rerun()


def lead_response_link(lead: dict[str, object]) -> str:
    token = str(lead.get("public_response_token") or "").strip()
    if not token and lead.get("id") is not None:
        token = storage.ensure_lead_response_token(int(lead["id"])) or ""
        lead = {**lead, "public_response_token": token}
    return message_generator.response_link_for_lead(lead)


def dashboard() -> None:
    if not require_login():
        return
    demo_header()
    st.title("Follow-Up Dashboard")
    st.caption("Daily work list for open estimates and follow-ups.")
    render_sales_intro()
    render_demo_status()
    how_it_works()
    status_filter = st.selectbox("Filter by status", ["All"] + STATUSES)
    leads = storage.list_leads(status_filter)
    if not leads:
        render_no_leads_state("dashboard")
        return
    rows = [
        {
            "Customer": x["customer_name"],
            "Service": x["service_type"],
            "Source": x["source"],
            "Status": x["status"],
            "Urgency": x["urgency"],
            "Age": age_label(x["created_at"]),
            "Next action": follow_up_action(x) or x["next_follow_up_at"] or "No action due",
            "Last event": x["last_event_at"],
        }
        for x in leads
    ]
    st.dataframe(rows, use_container_width=True, hide_index=True)
    st.subheader("Lead actions")
    for lead in leads:
        action = follow_up_action(lead) or "No action due"
        with st.expander(f"{lead['customer_name']} - {lead['service_type']} - {lead['status']}"):
            st.caption(f"{action} - {lead['email']} - {lead['phone']}")
            st.write(lead["description"])
            st.caption("Public response link")
            response_link = lead_response_link(lead)
            st.code(response_link, language="text")
            st.link_button(DASHBOARD_ACTION_LABELS["open_response"], response_link)
            scheduled_date = next_follow_up_date_value(lead)
            cols = st.columns([1, 1, 1, 1, 1, 1.2])
            if cols[0].button(DASHBOARD_ACTION_LABELS["view"], key=f"view_{lead['id']}", type="primary"):
                route_to_lead_detail(int(lead["id"]))
            if cols[1].button(DASHBOARD_ACTION_LABELS["followed_up"], key=f"followed_{lead['id']}"):
                mark_followed_up(int(lead["id"]))
            if cols[2].button(DASHBOARD_ACTION_LABELS["booked"], key=f"booked_{lead['id']}"):
                update_lead_status(int(lead["id"]), "Booked")
            if cols[3].button(DASHBOARD_ACTION_LABELS["lost"], key=f"lost_{lead['id']}"):
                update_lead_status(int(lead["id"]), "Lost")
            if cols[4].button(DASHBOARD_ACTION_LABELS["pause"], key=f"pause_{lead['id']}"):
                storage.update_lead(int(lead["id"]), status="Paused", paused=1, outcome="Paused")
                st.success("Lead paused.")
                st.rerun()
            new_date = cols[5].date_input("Next Follow-Up Date", value=scheduled_date, key=f"schedule_{lead['id']}")
            if cols[5].button(DASHBOARD_ACTION_LABELS["schedule"], key=f"save_date_{lead['id']}"):
                storage.update_lead(int(lead["id"]), next_follow_up_at=datetime.combine(new_date, time.min, tzinfo=UTC).isoformat())
                st.success("Follow-up date scheduled.")
                st.rerun()


def lead_detail() -> None:
    if not require_login():
        return
    demo_header()
    st.title("Lead Detail")
    leads = storage.list_leads()
    if not leads:
        render_no_leads_state("detail")
        return
    ids = [x["id"] for x in leads]
    selected = st.session_state.get("selected_lead_id")
    if selected not in ids:
        selected = ids[0]
    lead_id = st.selectbox("Lead", ids, index=ids.index(selected), format_func=lambda i: next(x["customer_name"] for x in leads if x["id"] == i))
    st.session_state["selected_lead_id"] = lead_id
    lead = storage.get_lead(lead_id)
    st.subheader(f"{lead['customer_name']} - {lead['service_type']}")
    st.caption("Edit the customer, estimate status, next follow-up, response link, and activity history for this LeadLoop Ops opportunity.")
    a, b, c, d = st.columns(4)
    a.metric("Status", lead["status"])
    b.metric("Urgency", lead["urgency"])
    c.metric("Assigned", lead["assigned_to"] or "Unassigned")
    d.metric("Age", age_label(lead["created_at"]))
    st.subheader("Customer information")
    st.write(f"Name: {lead['customer_name']}")
    st.write(f"Email: {lead['email']}")
    st.write(f"Phone: {lead['phone']}")
    st.write(f"Preferred contact: {lead['preferred_contact_method']}")
    st.subheader("Estimate / opportunity information")
    st.write(f"Service: {lead['service_type']}")
    st.write(f"Source: {lead['source']}")
    st.write(f"Description: {lead['description']}")
    st.write(f"Next follow-up: {lead['next_follow_up_at'] or 'Not scheduled'}")
    st.subheader("Public response link")
    st.caption("Use this simulated link when demonstrating how a customer can re-engage with the estimate follow-up workflow.")
    response_link = lead_response_link(lead)
    st.code(response_link, language="text")
    st.link_button(DASHBOARD_ACTION_LABELS["open_response"], response_link)
    st.subheader("Edit lead and follow-up")
    with st.form("lead_update"):
        c1, c2 = st.columns(2)
        status = c1.selectbox("Status", STATUSES, index=STATUSES.index(lead["status"]))
        assigned = c2.text_input("Assigned to", lead["assigned_to"] or "Office")
        paused = st.checkbox("Pause follow-up", value=bool(lead["paused"]))
        follow_up_date = st.date_input("Next follow-up date", value=next_follow_up_date_value(lead))
        note = st.text_area("Internal note")
        save = st.form_submit_button("Save updates", type="primary")
    if save:
        storage.update_lead(
            lead_id,
            status=status,
            assigned_to=assigned,
            paused=int(paused),
            next_follow_up_at=datetime.combine(follow_up_date, time.min, tzinfo=UTC).isoformat(),
            outcome=status if status in {"Booked", "Lost", "Not Ready"} else None,
        )
        if note.strip():
            storage.add_internal_note(lead_id, note)
        st.success("Lead updated and audit event recorded.")
        st.rerun()
    action = follow_up_action(lead)
    st.subheader("Follow-up message")
    preview = f"Hi {lead['customer_name'].split()[0]}, this is {COMPANY} checking in about your {lead['service_type'].lower()} request. Do you have any questions or would you like help scheduling the next step?"
    edited_preview = st.text_area("Preview", preview, height=110, key=f"preview_{lead_id}")
    if st.button("Simulate follow-up"):
        storage.create_simulated_follow_up(lead_id, edited_preview, lead["preferred_contact_method"].lower())
        st.success("Follow-up simulated. No external message was sent.")
        st.rerun()
    if action:
        st.warning(f"Current action: {action}")
    st.subheader("Message history")
    st.dataframe(storage.list_lead_messages(lead_id), use_container_width=True, hide_index=True)
    st.subheader("Audit trail")
    st.dataframe(storage.list_lead_events(lead_id), use_container_width=True, hide_index=True)


def follow_up_queue() -> None:
    if not require_login():
        return
    demo_header()
    st.title("Follow-Up Queue")
    st.caption("Estimate Rescue rules surface only eligible LeadLoop Ops opportunities. Booked, lost, and paused leads stop here automatically.")
    leads = storage.list_follow_up_leads()
    if not leads:
        render_no_follow_ups_state()
        return
    rows = [{"Customer": x["customer_name"], "Service": x["service_type"], "Status": x["status"], "Due reason": follow_up_action(x), "Assigned": x["assigned_to"]} for x in leads]
    st.dataframe(rows, use_container_width=True, hide_index=True)


def weekly_report() -> None:
    if not require_login():
        return
    demo_header()
    st.title("Owner Weekly Summary")
    m = storage.weekly_summary()
    labels = [("New leads", "new_leads"), ("Acknowledged", "acknowledged"), ("Need follow-up", "needing_follow_up"), ("Follow-ups completed", "follow_ups_completed"), ("Booked", "booked"), ("Lost", "lost"), ("Pending", "pending")]
    cols = st.columns(4)
    for i, (label, key) in enumerate(labels):
        cols[i % 4].metric(label, m[key])
    st.info(f"This week, {m['new_leads']} leads came in. {m['acknowledged']} were acknowledged, {m['needing_follow_up']} need follow-up, {m['booked']} booked, {m['lost']} were lost, and {m['pending']} are still pending.")


def demo_controls() -> None:
    if not require_login():
        return
    demo_header()
    st.title("Demo Controls")
    how_it_works()
    st.write("Load eight fictional HVAC opportunities used in the five-minute sales walkthrough.")
    if st.button("Seed demo data", type="primary"):
        seed_demo_data()
        st.success("Demo data is ready.")
    if st.button("Reset and reseed demo data"):
        storage.reset_leadloop_demo_data()
        seed_demo_data()
        st.success("Demo data reset.")


def render_quote_customer_response(quote: dict[str, object]) -> None:
    demo_header()
    st.title("Estimate Response")
    st.write(f"Responding to the {quote['service_type']} estimate for {quote['customer_name']}.")
    with st.form("customer_response"):
        response_type = st.radio(
            "What would you like to do?",
            ["book", "question", "deciding", "not_interested"],
            format_func=lambda value: {
                "book": "I want to book",
                "question": "I have a question",
                "deciding": "I am still deciding",
                "not_interested": "I am not interested",
            }[value],
        )
        notes = st.text_area("Anything else we should know?")
        submitted = st.form_submit_button("Send response", type="primary")
    if submitted:
        storage.create_customer_response(int(quote["id"]), response_type, notes)
        st.success("Thanks. Your response was recorded in the LeadLoop Ops demo.")


def render_lead_customer_response(lead: dict[str, object]) -> None:
    demo_header()
    st.title("LeadLoop Ops Response")
    st.write(f"Responding to the {lead['service_type']} opportunity for {lead['customer_name']}.")
    with st.form("lead_customer_response"):
        response_type = st.radio(
            "What would you like to do?",
            ["still_interested", "need_more_time", "booked_elsewhere", "request_follow_up"],
            format_func=lambda value: {
                "still_interested": "Still interested",
                "need_more_time": "Need more time",
                "booked_elsewhere": "Booked elsewhere",
                "request_follow_up": "Request follow-up",
            }[value],
        )
        notes = st.text_area("Anything else we should know?")
        submitted = st.form_submit_button("Send response", type="primary")
    if submitted:
        storage.create_lead_customer_response(int(lead["id"]), response_type, notes)
        st.success("Thanks. Your response was recorded in the LeadLoop Ops demo.")


def public_customer_response() -> None:
    requested, token = message_generator.public_response_token(st.query_params)
    if not requested:
        return
    lead = storage.get_lead_by_token(token)
    if lead:
        render_lead_customer_response(lead)
        return
    quote = storage.get_quote_by_token(token)
    if quote:
        render_quote_customer_response(quote)
        return
    demo_header()
    st.title("Response Link")
    st.error("This response link is invalid or has expired.")


PAGES = {
    "Customer Estimate Request": request_form,
    "Operator Login": login_page,
    "Follow-Up Dashboard": dashboard,
    "Lead Detail": lead_detail,
    "Follow-Up Queue": follow_up_queue,
    "Weekly Summary": weekly_report,
    "Demo Controls": demo_controls,
}
LEGACY_PAGE_ALIASES = {"Operator Dashboard": "Follow-Up Dashboard"}


def safe_page_name(value: object) -> str:
    """Normalize stale session navigation to the public request page."""
    if value in LEGACY_PAGE_ALIASES:
        return LEGACY_PAGE_ALIASES[str(value)]
    return str(value) if value in PAGES else next(iter(PAGES))


def apply_page_selection(selected_page: str, current_page: str) -> bool:
    """Persist a sidebar page change and force Streamlit to render it immediately."""
    if selected_page == current_page:
        return False
    st.session_state["page"] = selected_page
    st.rerun()
    return True


def main() -> None:
    public_requested, _ = message_generator.public_response_token(st.query_params)
    if public_requested:
        public_customer_response()
        return
    st.sidebar.title("LeadLoop Ops")
    st.sidebar.caption(POSITIONING)
    if st.session_state.get("logged_in") and st.sidebar.button("Log out"):
        st.session_state.clear()
        st.rerun()
    page_names = list(PAGES)
    current = safe_page_name(st.session_state.get("page"))
    st.session_state["page"] = current
    page = st.sidebar.radio("Navigation", page_names, index=page_names.index(current), key="nav_page")
    apply_page_selection(page, current)
    PAGES[page]()


if __name__ == "__main__":
    main()
