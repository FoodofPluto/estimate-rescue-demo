# Estimate Rescue

Estimate Rescue is a lightweight Streamlit + SQLite MVP for local service businesses that send quotes and then forget to follow up. It helps an owner see which estimates need attention, draft a useful follow-up, send or record the email, and track whether the quote was won, lost, or still pending.

The demo business is **Blue Ridge Auto Detail**, a fake auto detailing shop with sample ceramic coating, interior cleaning, paint correction, maintenance, and fleet wash opportunities.

## Demo Story

Blue Ridge Auto Detail sends several estimates each week. Some customers are ready to book, some have questions, and some simply need a timely nudge. Estimate Rescue gives the operator a simple queue of open quotes, a deterministic recovery score, an editable follow-up message, and a public response link customers can use without logging in.

The goal is not to be a full CRM. It is a focused small-business workflow demo: recover unsold quotes before they go cold.

## Screens And Pages

- **Public Demo Home**: explains the problem and demo business.
- **Operator Login**: uses `ADMIN_PASSWORD`; no third-party auth.
- **Operator Dashboard**: shows open quotes, due follow-ups, overdue quotes, open value, won value, lost value, recent activity, and top recovery opportunities.
- **Add Quote**: creates a quote and assigns a follow-up due date.
- **Follow-Up Queue**: lists due and overdue opportunities with score and suggested next action.
- **Quote Detail**: shows quote context, message generation, follow-up history, customer responses, and manual status updates.
- **Customer Response Page**: lets a customer respond from a tokenized public link.
- **Settings / Message Templates**: edits business settings and simple `$variable` templates.

## Local Setup

```bash
cd estimate-rescue-demo
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
streamlit run app.py
```

Set `ADMIN_PASSWORD` in `.env` before using operator pages. If `.env` is missing, the app still starts; operator pages stay locked until `ADMIN_PASSWORD` is configured.

## Environment Variables

| Variable | Required | Purpose |
| --- | --- | --- |
| `ADMIN_PASSWORD` | Yes for operator pages | Simple local/demo login password. |
| `RESEND_API_KEY` | No | Enables live email sending through Resend. |
| `RESEND_FROM_EMAIL` | No | Sender address used by Resend. |
| `OWNER_EMAIL` | No | Reply-to and default owner contact. |
| `OPENAI_API_KEY` | No | Enables optional AI follow-up helper. |
| `APP_BASE_URL` | Recommended | Base URL for customer response links, such as `http://localhost:8501`. |
| `DATABASE_PATH` | No | SQLite file path. Defaults to `estimate_rescue.db`. |

`.env.example` contains placeholders only. Do not commit `.env` or Streamlit secrets.

## Email Setup

The app uses Resend through Python's standard `urllib.request`.

If `RESEND_API_KEY` or `RESEND_FROM_EMAIL` is missing, sending does not crash. The app records the follow-up with `email_disabled`, which keeps the local demo useful without any external service.

The Resend request includes:

- `Authorization: Bearer <RESEND_API_KEY>`
- `Content-Type: application/json`
- `Accept: application/json`
- `User-Agent: EstimateRescueStreamlit/1.0`

## OpenAI Optional Helper

Deterministic template logic is the default and the app works without OpenAI. If `OPENAI_API_KEY` is set, the Quote Detail page can try an AI-generated draft. The deterministic version remains the fallback.

Generated messages are intentionally conservative: no fake discounts, no fake scarcity, no guarantees, and no unsupported claims.

## Customer Response Links

Each quote gets a unique public response token. When `APP_BASE_URL` is set, follow-up messages can include a link like:

```text
http://localhost:8501/?page=Customer+Response+Page&token=<token>
```

The customer can choose:

- I want to book
- I have a question
- I am still deciding
- Not interested anymore

The response updates quote status and writes an activity log entry.

## Seed Demo Data

The app seeds demo data automatically when the quotes table is empty. You can also run:

```bash
python seed_data.py
```

The seeded demo quotes are idempotent and will not duplicate endlessly.

## Tests

```bash
python -m py_compile app.py config.py storage.py quote_logic.py message_generator.py emailer.py seed_data.py
pytest
```

Tests cover database initialization, quote creation, dashboard metrics, follow-up queue logic, seed idempotency, customer response status mapping, disabled email behavior, message generation, template values, and Resend request construction.

## Streamlit Cloud Deployment Notes

1. Push the project without `.env`, `*.db`, `.pytest_cache/`, or virtualenv folders.
2. Add secrets in Streamlit Cloud for `ADMIN_PASSWORD`, `APP_BASE_URL`, and any optional Resend/OpenAI settings.
3. Leave `DATABASE_PATH` as the default unless you need a custom file location.
4. Remember that SQLite on Streamlit Cloud is suitable for a portfolio demo, not durable production storage.

## Portfolio Positioning

Estimate Rescue complements **Lead Rescue** by focusing on the post-estimate stage instead of new lead capture. Together, they show a practical small-business automation theme: capture demand, follow up at the right time, and keep the owner focused on revenue opportunities.

## Known Limitations

- No multi-user accounts or authentication provider.
- No SMS, calendar, Stripe, or CRM sync.
- No durable cloud database.
- Public response links are tokenized but not authenticated.
- Email deliverability depends on a correctly configured Resend domain.
- The recovery score is deterministic and intentionally simple.
