"""Email integration for Resend with graceful local-demo behavior."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from config import get_settings

RESEND_URL = "https://api.resend.com/emails"


def build_resend_request(
    *,
    api_key: str,
    from_email: str,
    to_email: str,
    subject: str,
    body: str,
    reply_to: str | None = None,
) -> urllib.request.Request:
    """Build a Resend API request without sending it."""
    payload: dict[str, Any] = {
        "from": from_email,
        "to": [to_email],
        "subject": subject,
        "text": body,
    }
    if reply_to:
        payload["reply_to"] = reply_to

    return urllib.request.Request(
        RESEND_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "EstimateRescueStreamlit/1.0",
        },
        method="POST",
    )


def send_email(
    *,
    to_email: str,
    subject: str,
    body: str,
    from_email: str | None = None,
    reply_to: str | None = None,
) -> dict[str, Any]:
    """Send an email through Resend or return a disabled result if unconfigured."""
    cfg = get_settings()
    sender = from_email or cfg.resend_from_email
    if not cfg.resend_api_key or not sender:
        return {
            "ok": False,
            "status": "email_disabled",
            "message": "Email sending is disabled because RESEND_API_KEY or RESEND_FROM_EMAIL is missing.",
        }

    request = build_resend_request(
        api_key=cfg.resend_api_key,
        from_email=sender,
        to_email=to_email,
        subject=subject,
        body=body,
        reply_to=reply_to or cfg.owner_email,
    )

    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            data = response.read().decode("utf-8")
            return {"ok": True, "status": "sent", "response": data}
    except urllib.error.HTTPError as exc:
        return {
            "ok": False,
            "status": "send_failed",
            "message": f"Resend returned HTTP {exc.code}.",
        }
    except urllib.error.URLError:
        return {
            "ok": False,
            "status": "send_failed",
            "message": "Email service could not be reached.",
        }
    except Exception:
        return {
            "ok": False,
            "status": "send_failed",
            "message": "Email sending failed unexpectedly.",
        }
