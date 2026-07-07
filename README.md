# LeadLoop Ops

LeadLoop Ops helps small home-service companies respond to every web lead quickly and follow up every open estimate so fewer jobs fall through the cracks.

This Streamlit + SQLite sales demo is configured for the fictional HVAC company **Blue Ridge Comfort Pros**. It demonstrates public lead intake, immediate simulated acknowledgment, an internal operator dashboard, deterministic estimate follow-up, opportunity outcomes, audit history, and an owner weekly summary. It supplements an existing CRM; it is not a CRM replacement.

## Run locally

```powershell
cd C:\Users\andro\Projects\estimate-rescue-demo
pip install -r requirements.txt
$env:ADMIN_PASSWORD="demo"
python seed_data.py
streamlit run app.py
```

Operator pages remain locked when `ADMIN_PASSWORD` is absent. The customer request page remains public.

## Demo flow

1. Submit a request under **Customer Estimate Request**.
2. Log in and open **Follow-Up Dashboard**; the request appears with its next action.
3. Open **Lead Detail** to assign it, change its status, add a note, or preview/simulate a follow-up.
4. Review rule-based work in **Follow-Up Queue**.
5. Show the results in **Weekly Summary**.

Use **Demo Controls → Reset and reseed demo data** for a clean walkthrough, or run `python seed_data.py`. Seeding is idempotent and adds only missing fictional records; it does not overwrite homeowner submissions.

## Messaging safety

LeadLoop Ops workflow messages are always recorded as `simulated`; no email or SMS leaves the app. Estimate Rescue is the estimate follow-up workflow inside LeadLoop Ops. The legacy optional Resend module remains in the repository for compatibility but is not called by the LeadLoop UI. No credentials are stored in source.

## Tests

```powershell
python -m py_compile app.py config.py storage.py leadloop_logic.py seed_data.py emailer.py
pytest --basetemp=.pytest-tmp
```

SQLite is appropriate for this portfolio demo, not multi-user production deployment. There is no CRM sync, SMS provider, scheduling integration, or multi-tenant account model.

## Intentionally out of scope

LeadLoop Ops is a managed lead-response and estimate-follow-up workflow, not a full CRM or autonomous messaging platform. Real outbound messaging, CRM synchronization, billing, multi-tenancy, and production-grade authentication are intentionally excluded from this sales demo.
