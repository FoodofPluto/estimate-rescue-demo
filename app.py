"""LeadLoop Ops: lead response and estimate follow-up demo."""

from __future__ import annotations

from datetime import UTC, date, datetime, time
import re

import streamlit as st
import streamlit.components.v1 as components

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
DASHBOARD_ACTION_LABELS = {"view": "View/Edit Lead", "open_response": "Open Response Link"}
LEAD_STATUS_OPTIONS = ["New", "Needs Follow-Up", "Followed Up", "Booked", "Lost", "Paused"]
# TODO: Promote this to a persisted operator-managed list if the demo grows beyond fixed options.
LEAD_ACTION_OPTIONS = [
    "Call customer",
    "Text customer",
    "Email customer",
    "Send estimate",
    "Revise estimate",
    "Schedule visit",
    "Waiting on customer",
    "Customer asked question",
    "Mark as booked",
    "Mark as lost",
    "Pause follow-up",
    "No further action",
]
ESTIMATE_STATUS_OPTIONS = ["Draft", "Sent", "Revised", "Approved", "Declined"]
MESSAGE_PURPOSE_OPTIONS = ["Check-in", "Estimate reminder", "Answer customer question", "Booking nudge", "Revised estimate notice"]
MESSAGE_TONE_OPTIONS = ["Professional", "Friendly", "Brief", "Urgent"]

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


def next_follow_up_time_value(lead: dict[str, object]) -> time:
    raw = str(lead.get("next_follow_up_at") or "")
    if raw:
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).time().replace(microsecond=0)
        except ValueError:
            pass
    return time(9, 0)


def combine_follow_up_at(enabled: bool, follow_up_date: date, follow_up_time: time) -> str | None:
    if not enabled:
        return None
    return datetime.combine(follow_up_date, follow_up_time, tzinfo=UTC).replace(microsecond=0).isoformat()


def format_timestamp(value: object, *, use_24_hour: bool = False, fallback: str = "Not recorded") -> str:
    text = str(value or "").strip()
    if not text:
        return fallback
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return text
    month = parsed.strftime("%b")
    day = parsed.day
    year = parsed.year
    clock = parsed.strftime("%H:%M") if use_24_hour else parsed.strftime("%I:%M %p").lstrip("0")
    return f"{month} {day}, {year} · {clock}"


def display_value(value: object, fallback: str = "Not provided") -> str:
    text = str(value or "").strip()
    return text or fallback


def money_value(value: object) -> str:
    if value in (None, ""):
        return "Not estimated"
    try:
        return f"${float(value):,.0f}"
    except (TypeError, ValueError):
        return str(value)


def lead_event_summary(event: dict[str, object] | None) -> str:
    if not event:
        return "No recent activity"
    timestamp = format_timestamp(event.get("timestamp"), fallback="")
    message = display_value(event.get("message"), "")
    return f"{timestamp} - {message}" if timestamp else message


def latest_lead_event(events: list[dict[str, object]], event_type: str | None = None) -> dict[str, object] | None:
    for event in events:
        if event_type is None or event.get("event_type") == event_type:
            return event
    return None


def latest_follow_up(messages: list[dict[str, object]], events: list[dict[str, object]]) -> str:
    for message in messages:
        if message.get("template_name") == "estimate_follow_up":
            return format_timestamp(message.get("sent_at") or message.get("scheduled_at"), fallback="Recorded")
    return lead_event_summary(latest_lead_event(events, "follow_up_completed"))


def lead_action_context(
    lead: dict[str, object],
    response_link: str,
    events: list[dict[str, object]] | None = None,
    messages: list[dict[str, object]] | None = None,
) -> dict[str, str]:
    events = events or []
    messages = messages or []
    recent_customer_response = latest_lead_event(events, "customer_response")
    recent_activity = recent_customer_response or latest_lead_event(events)
    return {
        "Customer": display_value(lead.get("customer_name")),
        "Email": display_value(lead.get("email")),
        "Phone": display_value(lead.get("phone")),
        "Estimate amount": money_value(lead.get("booked_value_estimate")),
        "Estimate status": display_value(lead.get("estimate_status"), "Draft"),
        "Current status": display_value(lead.get("status")),
        "Last follow-up": latest_follow_up(messages, events),
        "Next follow-up": format_timestamp(lead.get("next_follow_up_at"), fallback="Not scheduled"),
        "Most recent customer response or activity": lead_event_summary(recent_activity),
        "Public response link": response_link,
    }


def lead_detail_sections(lead: dict[str, object], response_link: str) -> dict[str, dict[str, str]]:
    return {
        "header": {
            "Customer": display_value(lead.get("customer_name")),
            "Status": display_value(lead.get("status")),
            "Estimate amount": money_value(lead.get("booked_value_estimate")),
            "Estimate status": display_value(lead.get("estimate_status"), "Draft"),
        },
        "contact": {
            "Email": display_value(lead.get("email")),
            "Phone": display_value(lead.get("phone")),
            "Preferred contact": display_value(lead.get("preferred_contact_method")),
            "Source": display_value(lead.get("source")),
        },
        "opportunity": {
            "Estimate amount": money_value(lead.get("booked_value_estimate")),
            "Service type": display_value(lead.get("service_type")),
            "Lead status": display_value(lead.get("status")),
            "Estimate status": display_value(lead.get("estimate_status"), "Draft"),
            "Urgency": display_value(lead.get("urgency")),
            "Assigned": display_value(lead.get("assigned_to"), "Unassigned"),
            "Notes": display_value(lead.get("description"), "No notes"),
        },
        "follow_up": {
            "Next follow-up": format_timestamp(lead.get("next_follow_up_at"), fallback="Not scheduled"),
            "Public response link": response_link,
        },
    }


def route_to_lead_detail(lead_id: int) -> None:
    st.session_state["selected_lead_id"] = lead_id
    st.session_state["page"] = "Lead Detail"
    st.session_state["pending_nav_page"] = "Lead Detail"
    st.session_state["scroll_to_top_lead_detail"] = True
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


def option_index(options: list[str], value: object, default: int = 0) -> int:
    text = str(value or "").strip()
    return options.index(text) if text in options else default


def ui_lead_status(value: object) -> str:
    return {
        "Contacted": "Followed Up",
        "Estimate Sent": "Needs Follow-Up",
        "Follow-Up Due": "Needs Follow-Up",
        "Not Ready": "Needs Follow-Up",
    }.get(str(value or "").strip(), str(value or "").strip() or "New")


def status_from_action(current_status: str, action: str) -> str:
    return {
        "Mark as booked": "Booked",
        "Mark as lost": "Lost",
        "Pause follow-up": "Paused",
        "No further action": current_status,
    }.get(action, current_status)


def parse_customer_response_event(event: dict[str, object] | None) -> dict[str, str] | None:
    if not event:
        return None
    raw_message = str(event.get("message") or "")
    message = raw_message
    notes_match = re.search(r"Notes:\s*(.*)$", raw_message)
    if notes_match:
        message = notes_match.group(1).strip()
    elif raw_message.lower().startswith("customer response:"):
        message = raw_message.split(":", 1)[1].strip().rstrip(".")
    metadata = str(event.get("metadata") or "")
    response_type = metadata.replace("response_type=", "").replace("_", " ").title() if metadata.startswith("response_type=") else "Customer response"
    return {
        "response_type": response_type,
        "message": message or "No message provided.",
        "submitted_at": format_timestamp(event.get("timestamp")),
        "source": "Public response link / customer response form",
        "suggested_next_step": suggested_next_step_for_response(response_type, message),
    }


def suggested_next_step_for_response(response_type: str, message: str) -> str:
    combined = f"{response_type} {message}".lower()
    if "question" in combined:
        return "Answer the customer's question, then schedule the next step."
    if "booked elsewhere" in combined:
        return "Mark as lost and stop follow-up."
    if "follow" in combined or "interested" in combined:
        return "Contact the customer and offer a visit or booking time."
    if "time" in combined:
        return "Schedule a later follow-up."
    return "Review feedback and choose the next action."


def customer_response_view_model(events: list[dict[str, object]]) -> dict[str, str] | None:
    return parse_customer_response_event(latest_lead_event(events, "customer_response"))


def render_customer_response_card(events: list[dict[str, object]]) -> None:
    response = customer_response_view_model(events)
    st.subheader("Customer Response")
    if not response:
        st.info("No customer feedback has been submitted from the demo response link yet.")
        return
    st.markdown(f"**Category:** {response['response_type']}")
    st.info(response["message"])
    st.caption(f"Submitted: {response['submitted_at']}")
    st.caption(f"Source: {response['source']}")
    st.markdown(f"**Suggested next step:** {response['suggested_next_step']}")


def render_lead_action_panel(lead: dict[str, object], *, compact: bool = False) -> None:
    lead_id = int(lead["id"])
    with st.form(f"lead_action_{lead_id}_{'compact' if compact else 'full'}"):
        cols = st.columns(2)
        current_status = cols[0].selectbox(
            "Current lead status",
            LEAD_STATUS_OPTIONS,
            index=option_index(LEAD_STATUS_OPTIONS, ui_lead_status(lead.get("status"))),
            key=f"status_action_{lead_id}_{compact}",
        )
        default_action = lead.get("next_action") or follow_up_action(lead) or "Call customer"
        next_action = cols[1].selectbox(
            "Next action",
            LEAD_ACTION_OPTIONS,
            index=option_index(LEAD_ACTION_OPTIONS, default_action),
            key=f"next_action_{lead_id}_{compact}",
        )
        schedule_follow_up = st.checkbox("Set follow-up date/time", value=bool(lead.get("next_follow_up_at")), key=f"schedule_enabled_{lead_id}_{compact}")
        date_col, time_col = st.columns(2)
        follow_up_date = date_col.date_input("Follow-up date", value=next_follow_up_date_value(lead), disabled=not schedule_follow_up, key=f"follow_date_{lead_id}_{compact}")
        follow_up_time = time_col.time_input("Follow-up time", value=next_follow_up_time_value(lead), disabled=not schedule_follow_up, key=f"follow_time_{lead_id}_{compact}")
        note = st.text_area("Internal operator note", value=str(lead.get("operator_note") or ""), height=90 if compact else 120, key=f"operator_note_{lead_id}_{compact}")
        save = st.form_submit_button("Save Lead Action", type="primary")
    if save:
        storage.save_lead_action(
            lead_id,
            status=status_from_action(current_status, next_action),
            next_action=next_action,
            follow_up_at=combine_follow_up_at(schedule_follow_up, follow_up_date, follow_up_time),
            operator_note=note,
        )
        st.success("Lead action saved.")
        st.rerun()


def render_estimate_editor(lead: dict[str, object], *, compact: bool = False) -> None:
    lead_id = int(lead["id"])
    with st.form(f"estimate_editor_{lead_id}_{'compact' if compact else 'full'}"):
        amount_value = float(lead.get("booked_value_estimate") or 0)
        amount = st.number_input("Estimate amount", min_value=0.0, value=amount_value, step=50.0, key=f"estimate_amount_{lead_id}_{compact}")
        title = st.text_input("Estimate/service title", value=str(lead.get("service_type") or ""), key=f"estimate_title_{lead_id}_{compact}")
        summary = st.text_area("Estimate summary or description", value=str(lead.get("description") or ""), height=80 if compact else 140, key=f"estimate_summary_{lead_id}_{compact}")
        status = st.selectbox("Estimate status", ESTIMATE_STATUS_OPTIONS, index=option_index(ESTIMATE_STATUS_OPTIONS, lead.get("estimate_status")), key=f"estimate_status_{lead_id}_{compact}")
        note = st.text_area("Internal estimate note", value=str(lead.get("estimate_note") or ""), height=70 if compact else 110, key=f"estimate_note_{lead_id}_{compact}")
        save = st.form_submit_button("Save Estimate", type="primary")
    if save:
        storage.update_lead_estimate(
            lead_id,
            amount=amount,
            title=title,
            summary=summary,
            estimate_status=status,
            estimate_note=note,
        )
        st.success("Estimate saved.")
        st.rerun()


def generate_lead_follow_up_draft(
    lead: dict[str, object],
    *,
    purpose: str = "Check-in",
    tone: str = "Professional",
    customer_feedback: dict[str, str] | None = None,
) -> str:
    first_name = str(lead.get("customer_name") or "there").split()[0]
    service = str(lead.get("service_type") or "your service")
    amount = money_value(lead.get("booked_value_estimate")).lower()
    status = str(lead.get("status") or "New")
    action = str(lead.get("next_action") or "follow up")
    feedback = f" I saw your note: \"{customer_feedback['message']}\"" if customer_feedback else ""
    opener = {
        "Friendly": "I wanted to check in",
        "Brief": "Quick check-in",
        "Urgent": "I wanted to make sure we do not miss the next step",
        "Professional": "I am following up",
    }.get(tone, "I am following up")
    purpose_line = {
        "Estimate reminder": f"about the {amount} estimate for {service}",
        "Answer customer question": f"about your question on {service}",
        "Booking nudge": f"to see if you would like to schedule {service}",
        "Revised estimate notice": f"with an update on your revised {service} estimate",
        "Check-in": f"about your {service} request",
    }.get(purpose, f"about your {service} request")
    return (
        f"Hi {first_name},\n\n"
        f"{opener} {purpose_line}.{feedback}\n\n"
        f"Current status on our side is {status}, and the next action is: {action}. "
        "Reply with any questions or a good time for the next step.\n\n"
        f"Thanks,\n{COMPANY}"
    )


def render_message_history(messages: list[dict[str, object]], events: list[dict[str, object]]) -> None:
    rows = []
    for message in messages:
        rows.append({
            "Time": format_timestamp(message.get("sent_at") or message.get("scheduled_at")),
            "Type": display_value(message.get("template_name")),
            "Source": display_value(message.get("channel")).title(),
            "Status": display_value(message.get("status")),
            "Message": display_value(message.get("preview_text")),
        })
    for event in events:
        if event.get("event_type") == "customer_response":
            response = parse_customer_response_event(event)
            rows.append({
                "Time": response["submitted_at"] if response else format_timestamp(event.get("timestamp")),
                "Type": "Customer response",
                "Source": "Customer",
                "Status": display_value(event.get("event_type")),
                "Message": response["message"] if response else display_value(event.get("message")),
            })
    st.dataframe(rows, use_container_width=True, hide_index=True)


def render_audit_trail(events: list[dict[str, object]]) -> None:
    rows = [
        {
            "Time": format_timestamp(event.get("timestamp")),
            "Event": display_value(event.get("event_type")).replace("_", " ").title(),
            "Actor": display_value(event.get("actor")),
            "Note": display_value(event.get("message")),
        }
        for event in events
        if event.get("event_type") != "customer_response"
    ]
    st.dataframe(rows, use_container_width=True, hide_index=True)


def valid_selected_lead_id(leads: list[dict[str, object]], selected: object) -> object | None:
    ids = [lead["id"] for lead in leads]
    return selected if selected in ids else (ids[0] if ids else None)


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
            "Next action": x.get("next_action") or follow_up_action(x) or "No action due",
            "Last event": format_timestamp(x["last_event_at"], fallback="No activity"),
        }
        for x in leads
    ]
    st.dataframe(rows, use_container_width=True, hide_index=True)
    st.subheader("Lead actions")
    for lead in leads:
        action = follow_up_action(lead) or "No action due"
        with st.expander(f"{lead['customer_name']} - {lead['service_type']} - {lead['status']}"):
            response_link = lead_response_link(lead)
            context = lead_action_context(
                lead,
                response_link,
                events := storage.list_lead_events(int(lead["id"])),
                storage.list_lead_messages(int(lead["id"])),
            )
            top_left, top_mid, top_right = st.columns([1.2, 1.1, 1])
            top_left.markdown(f"**{context['Customer']}**")
            top_left.caption(f"{context['Email']} | {context['Phone']}")
            top_mid.metric("Estimate", context["Estimate amount"])
            top_mid.caption(f"Estimate status: {context['Estimate status']}")
            top_right.caption(f"Lead status: {context['Current status']}")
            top_right.caption(f"Action: {lead.get('next_action') or action}")
            top_right.caption(f"Next: {context['Next follow-up']}")

            detail_left, detail_right = st.columns([1.4, 1])
            detail_left.write(lead["description"])
            detail_left.caption(f"Last follow-up: {context['Last follow-up']}")
            detail_right.caption("Public response link")
            detail_right.code(context["Public response link"], language="text")
            detail_right.link_button(DASHBOARD_ACTION_LABELS["open_response"], context["Public response link"])
            render_customer_response_card(events)
            st.subheader("Lead Status & Next Action")
            render_lead_action_panel(lead, compact=True)
            st.subheader("Compact Estimate Editor")
            render_estimate_editor(lead, compact=True)
            if st.button(DASHBOARD_ACTION_LABELS["view"], key=f"view_{lead['id']}", type="primary"):
                route_to_lead_detail(int(lead["id"]))


def lead_detail() -> None:
    if not require_login():
        return
    demo_header()
    if st.session_state.pop("scroll_to_top_lead_detail", False):
        components.html("<script>window.parent.scrollTo(0, 0);</script>", height=0)
    st.title("Lead Detail")
    leads = storage.list_leads()
    if not leads:
        render_no_leads_state("detail")
        return
    ids = [x["id"] for x in leads]
    selected = st.session_state.get("selected_lead_id")
    selected = valid_selected_lead_id(leads, selected)
    lead_id = st.selectbox("Lead", ids, index=ids.index(selected), format_func=lambda i: next(x["customer_name"] for x in leads if x["id"] == i))
    st.session_state["selected_lead_id"] = lead_id
    lead = storage.get_lead(lead_id)
    response_link = lead_response_link(lead)
    sections = lead_detail_sections(lead, response_link)

    header = sections["header"]
    st.subheader(header["Customer"])
    h1, h2, h3, h4 = st.columns(4)
    h1.metric("Status", header["Status"])
    h2.metric("Estimate", header["Estimate amount"])
    h3.metric("Estimate status", header["Estimate status"])
    h4.metric("Age", age_label(lead["created_at"]))

    contact, opportunity = st.columns([1, 1.4])
    with contact:
        st.subheader("Contact")
        st.write(f"Email: {sections['contact']['Email']}")
        st.write(f"Phone: {sections['contact']['Phone']}")
        st.write(f"Preferred contact: {sections['contact']['Preferred contact']}")
        st.write(f"Source: {sections['contact']['Source']}")
    with opportunity:
        st.subheader("Estimate / opportunity")
        st.write(f"Service type: {sections['opportunity']['Service type']}")
        st.write(f"Lead status: {sections['opportunity']['Lead status']}")
        st.write(f"Estimate status: {sections['opportunity']['Estimate status']}")
        st.write(f"Assigned: {sections['opportunity']['Assigned']}")
        st.write(f"Notes: {sections['opportunity']['Notes']}")

    st.subheader("Follow-up")
    f1, f2 = st.columns([1, 1.4])
    f1.write(f"Next follow-up: {sections['follow_up']['Next follow-up']}")
    f2.caption("Public response link")
    f2.code(sections["follow_up"]["Public response link"], language="text")
    f2.link_button(DASHBOARD_ACTION_LABELS["open_response"], sections["follow_up"]["Public response link"])

    st.subheader("Lead Status & Next Action")
    render_lead_action_panel(lead)

    st.subheader("Estimate Editor")
    render_estimate_editor(lead)

    with st.form("lead_assignment"):
        assigned = st.text_input("Assigned to", lead["assigned_to"] or "Office")
        note = st.text_area("Internal note")
        save = st.form_submit_button("Save updates", type="primary")
    if save:
        storage.update_lead(
            lead_id,
            assigned_to=assigned,
        )
        if note.strip():
            storage.add_internal_note(lead_id, note)
        st.success("Lead updated and audit event recorded.")
        st.rerun()
    events = storage.list_lead_events(lead_id)
    customer_feedback = customer_response_view_model(events)
    render_customer_response_card(events)
    action = lead.get("next_action") or follow_up_action(lead)
    st.subheader("Follow-Up Message Composer")
    st.caption("Demo mode: generated or saved drafts are logged here only. No email or SMS is sent automatically.")
    purpose = st.selectbox("Message purpose", MESSAGE_PURPOSE_OPTIONS, key=f"message_purpose_{lead_id}")
    tone = st.selectbox("Tone", MESSAGE_TONE_OPTIONS, key=f"message_tone_{lead_id}")
    draft_key = f"message_draft_{lead_id}"
    if draft_key not in st.session_state:
        st.session_state[draft_key] = generate_lead_follow_up_draft(lead, purpose=purpose, tone=tone, customer_feedback=customer_feedback)
    if st.button("Generate Follow-Up Draft", key=f"generate_draft_{lead_id}"):
        st.session_state[draft_key] = generate_lead_follow_up_draft(lead, purpose=purpose, tone=tone, customer_feedback=customer_feedback)
    edited_preview = st.text_area("Message body", st.session_state[draft_key], height=180, key=f"preview_{lead_id}")
    draft_cols = st.columns([1, 1])
    if draft_cols[0].button("Save Draft / Log Message", key=f"save_draft_{lead_id}", type="primary"):
        storage.save_follow_up_draft(lead_id, edited_preview, str(lead["preferred_contact_method"] or "email").lower())
        st.success("Draft saved to message history. No external message was sent.")
        st.rerun()
    draft_cols[1].code(edited_preview, language="text")
    if action:
        st.warning(f"Current action: {action}")
    st.subheader("Activity")
    messages_col, events_col = st.columns(2)
    lead_messages = storage.list_lead_messages(lead_id)
    with messages_col:
        st.markdown("**Message History**")
        st.caption("Customer-facing or operator-written messages, drafts, generated follow-ups, and customer responses.")
        render_message_history(lead_messages, events)
    with events_col:
        st.markdown("**Audit Trail**")
        st.caption("Internal system events such as lead creation, status changes, estimate edits, action changes, and record updates.")
        render_audit_trail(events)


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


def prepare_sidebar_navigation(page_names: list[str]) -> str:
    """Return the canonical page and prepare nav_page before its widget exists."""
    current = safe_page_name(st.session_state.get("page"))
    pending_page = st.session_state.pop("pending_nav_page", None)
    if pending_page is not None:
        current = safe_page_name(pending_page)
        st.session_state["nav_page"] = current
    elif "nav_page" not in st.session_state:
        st.session_state["nav_page"] = current
    elif st.session_state["nav_page"] not in page_names:
        st.session_state["nav_page"] = current
    st.session_state["page"] = current
    return current


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
    current = prepare_sidebar_navigation(page_names)
    page = st.sidebar.radio("Navigation", page_names, index=page_names.index(current), key="nav_page")
    apply_page_selection(page, current)
    PAGES[page]()


if __name__ == "__main__":
    main()
