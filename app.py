"""LeadLoop Ops: lead response and estimate follow-up demo."""

from __future__ import annotations

from datetime import UTC, datetime

import streamlit as st

import storage
from config import get_settings
from leadloop_logic import STATUSES, follow_up_action
from seed_data import seed_demo_data

COMPANY = "Blue Ridge Comfort Pros"
POSITIONING = "LeadLoop Ops helps small home-service companies respond to every web lead quickly and follow up every open estimate so fewer jobs fall through the cracks."

st.set_page_config(page_title="LeadLoop Ops", page_icon="🔁", layout="wide")
storage.init_db()


def demo_header() -> None:
    st.caption("🟠 DEMO MODE · No real email or SMS is sent")


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
    st.write("Tell us what is happening and our office will follow up shortly.")
    with st.form("estimate_request", clear_on_submit=True):
        left, right = st.columns(2)
        name = left.text_input("Name *")
        email = right.text_input("Email *")
        phone = left.text_input("Phone *")
        service = right.selectbox("Service type", ["AC repair", "Heating repair", "Heat pump replacement", "Seasonal maintenance", "Mini-split quote", "Thermostat service", "Other"])
        urgency = left.selectbox("Urgency", ["Routine", "Soon", "Urgent — no heating or cooling"])
        contact = right.selectbox("Preferred contact method", ["Email", "Phone", "Text"])
        description = st.text_area("Describe the problem or project *")
        consent = st.checkbox("I agree that Blue Ridge Comfort Pros may contact me about this request.")
        submitted = st.form_submit_button("Send request", type="primary")
    if submitted:
        if not all([name.strip(), email.strip(), phone.strip(), description.strip(), consent]):
            st.error("Complete the required fields and communication acknowledgment.")
            return
        lead_id = storage.create_lead(customer_name=name, email=email, phone=phone, service_type=service,
            urgency=urgency, preferred_contact_method=contact, description=description)
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


def dashboard() -> None:
    if not require_login(): return
    demo_header(); st.title("Operator Dashboard")
    st.caption("Every open opportunity and its next action in one place.")
    status_filter = st.selectbox("Filter by status", ["All"] + STATUSES)
    leads = storage.list_leads(status_filter)
    if not leads:
        st.info("No leads match this view. Seed demo data from Demo Controls.")
        return
    rows = [{"Customer": x["customer_name"], "Service": x["service_type"], "Source": x["source"],
        "Status": x["status"], "Urgency": x["urgency"], "Age": age_label(x["created_at"]),
        "Next action": follow_up_action(x) or x["next_follow_up_at"] or "No action due",
        "Last event": x["last_event_at"]} for x in leads]
    st.dataframe(rows, use_container_width=True, hide_index=True)
    selected = st.selectbox("Open lead", [x["id"] for x in leads], format_func=lambda i: next(f"{x['customer_name']} — {x['service_type']}" for x in leads if x["id"] == i))
    if st.button("View lead detail", type="primary"):
        st.session_state["selected_lead_id"] = selected; st.session_state["page"] = "Lead Detail"; st.rerun()


def lead_detail() -> None:
    if not require_login(): return
    demo_header(); st.title("Lead Detail")
    leads = storage.list_leads()
    if not leads: st.info("No leads yet."); return
    ids = [x["id"] for x in leads]
    selected = st.session_state.get("selected_lead_id")
    if selected not in ids: selected = ids[0]
    lead_id = st.selectbox("Lead", ids, index=ids.index(selected), format_func=lambda i: next(x["customer_name"] for x in leads if x["id"] == i))
    st.session_state["selected_lead_id"] = lead_id
    lead = storage.get_lead(lead_id)
    st.subheader(f"{lead['customer_name']} · {lead['service_type']}")
    a,b,c,d = st.columns(4); a.metric("Status", lead["status"]); b.metric("Urgency", lead["urgency"]); c.metric("Assigned", lead["assigned_to"] or "Unassigned"); d.metric("Age", age_label(lead["created_at"]))
    st.write(lead["description"]); st.caption(f"{lead['email']} · {lead['phone']} · Prefers {lead['preferred_contact_method']}")
    with st.form("lead_update"):
        c1,c2 = st.columns(2)
        status = c1.selectbox("Status", STATUSES, index=STATUSES.index(lead["status"]))
        assigned = c2.text_input("Assigned to", lead["assigned_to"] or "Office")
        paused = st.checkbox("Pause follow-up", value=bool(lead["paused"]))
        note = st.text_area("Internal note")
        save = st.form_submit_button("Save updates", type="primary")
    if save:
        storage.update_lead(lead_id, status=status, assigned_to=assigned, paused=int(paused), outcome=status if status in {"Booked","Lost","Not Ready"} else None)
        if note.strip(): storage.add_internal_note(lead_id, note)
        st.success("Lead updated and audit event recorded."); st.rerun()
    action = follow_up_action(lead)
    st.subheader("Follow-up message")
    preview = f"Hi {lead['customer_name'].split()[0]}, this is {COMPANY} checking in about your {lead['service_type'].lower()} request. Do you have any questions or would you like help scheduling the next step?"
    edited_preview = st.text_area("Preview", preview, height=110, key=f"preview_{lead_id}")
    if st.button("Simulate follow-up"):
        storage.create_simulated_follow_up(lead_id, edited_preview, lead["preferred_contact_method"].lower())
        st.success("Follow-up simulated. No external message was sent."); st.rerun()
    if action: st.warning(f"Current action: {action}")
    st.subheader("Message history"); st.dataframe(storage.list_lead_messages(lead_id), use_container_width=True, hide_index=True)
    st.subheader("Audit trail"); st.dataframe(storage.list_lead_events(lead_id), use_container_width=True, hide_index=True)


def follow_up_queue() -> None:
    if not require_login(): return
    demo_header(); st.title("Follow-Up Queue"); st.caption("Deterministic rules surface only eligible leads. Booked, lost, and paused leads stop here automatically.")
    leads = storage.list_follow_up_leads()
    if not leads: st.success("No follow-ups are due."); return
    rows = [{"Customer": x["customer_name"], "Service": x["service_type"], "Status": x["status"], "Due reason": follow_up_action(x), "Assigned": x["assigned_to"]} for x in leads]
    st.dataframe(rows, use_container_width=True, hide_index=True)


def weekly_report() -> None:
    if not require_login(): return
    demo_header(); st.title("Owner Weekly Summary")
    m = storage.weekly_summary(); labels = [("New leads", "new_leads"), ("Acknowledged", "acknowledged"), ("Need follow-up", "needing_follow_up"), ("Follow-ups completed", "follow_ups_completed"), ("Booked", "booked"), ("Lost", "lost"), ("Pending", "pending")]
    cols = st.columns(4)
    for i,(label,key) in enumerate(labels): cols[i % 4].metric(label, m[key])
    st.info(f"This week, {m['new_leads']} leads came in. {m['acknowledged']} were acknowledged, {m['needing_follow_up']} need follow-up, {m['booked']} booked, {m['lost']} were lost, and {m['pending']} are still pending.")


def demo_controls() -> None:
    if not require_login(): return
    demo_header(); st.title("Demo Controls")
    st.write("Load eight fictional HVAC opportunities used in the five-minute sales walkthrough.")
    if st.button("Seed demo data", type="primary"):
        seed_demo_data(); st.success("Demo data is ready.")
    if st.button("Reset and reseed demo data"):
        storage.reset_leadloop_demo_data(); seed_demo_data(); st.success("Demo data reset.")


PAGES = {"Customer Estimate Request": request_form, "Operator Login": login_page, "Operator Dashboard": dashboard,
    "Lead Detail": lead_detail, "Follow-Up Queue": follow_up_queue, "Weekly Summary": weekly_report, "Demo Controls": demo_controls}


def safe_page_name(value: object) -> str:
    """Normalize stale session navigation to the public request page."""
    return str(value) if value in PAGES else next(iter(PAGES))


def main() -> None:
    st.sidebar.title("LeadLoop Ops")
    st.sidebar.caption(POSITIONING)
    if st.session_state.get("logged_in") and st.sidebar.button("Log out"):
        st.session_state.clear(); st.rerun()
    page_names = list(PAGES); current = safe_page_name(st.session_state.get("page"))
    st.session_state["page"] = current
    page = st.sidebar.radio("Navigation", page_names, index=page_names.index(current))
    if page != current: st.session_state["page"] = page
    PAGES[page]()


if __name__ == "__main__": main()
