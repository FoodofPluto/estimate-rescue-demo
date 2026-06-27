"""Follow-up message generation for Estimate Rescue."""

from __future__ import annotations

import json
import urllib.request
from string import Template
from typing import Any

from config import get_settings
from quote_logic import format_currency


TONE_OPENERS = {
    "friendly": "I wanted to check in on the estimate we prepared for you.",
    "professional": "I am following up regarding your recent estimate.",
    "casual": "Just checking in on the estimate we put together for you.",
    "urgent": "I wanted to make sure your estimate did not get buried.",
    "premium": "I wanted to personally follow up on your detailing estimate.",
}


def response_link_for_quote(quote: dict[str, Any]) -> str:
    if quote.get("response_link"):
        return str(quote["response_link"])
    cfg = get_settings()
    token = quote.get("public_response_token")
    if token:
        base_url = cfg.app_base_url.rstrip("/") if cfg.app_base_url else ""
        return f"{base_url}/?page=Customer+Response+Page&token={token}"
    return ""


def template_values(quote: dict[str, Any], business_settings: dict[str, Any]) -> dict[str, str]:
    """Return supported template variables for follow-up messages."""
    return {
        "customer_name": quote.get("customer_name", "there"),
        "business_name": business_settings.get("business_name") or "Blue Ridge Auto Detail",
        "service_type": quote.get("service_type", "your service"),
        "quote_amount": format_currency(quote.get("quote_amount")),
        "response_link": response_link_for_quote(quote),
    }


def _render_template(text: str, values: dict[str, str]) -> str:
    return Template(text).safe_substitute(values)


def render_saved_template(
    template: dict[str, Any], quote: dict[str, Any], business_settings: dict[str, Any]
) -> dict[str, str]:
    """Render a persisted operator template for a Quote Detail draft."""
    values = template_values(quote, business_settings)
    return {
        "subject": _render_template(str(template.get("subject_template") or ""), values),
        "body": _render_template(str(template.get("body_template") or ""), values),
    }


def generate_follow_up_message(
    quote: dict[str, Any],
    business_settings: dict[str, Any],
    template_key: str = "first_follow_up",
    tone: str = "friendly",
) -> dict[str, str]:
    """Generate a deterministic follow-up subject and body."""
    values = template_values(quote, business_settings)
    response_link = values["response_link"]

    templates = {
        "first_follow_up": {
            "subject": "Following up on your $service_type estimate",
            "body": (
                "Hi $customer_name,\n\n"
                f"{TONE_OPENERS.get(tone, TONE_OPENERS['friendly'])} "
                "The estimate for $service_type is $quote_amount.\n\n"
                "If you are ready to move forward, have a question, or are still deciding, "
                "you can reply here"
                + (" or use this quick response link: $response_link" if response_link else "")
                + ".\n\n"
                "Thanks,\n$business_name"
            ),
        },
        "question_follow_up": {
            "subject": "Any questions about your $service_type estimate?",
            "body": (
                "Hi $customer_name,\n\n"
                "I wanted to see if any questions came up about your $service_type estimate "
                "from $business_name. The quoted amount is $quote_amount.\n\n"
                "Reply any time and we can help you decide what makes sense for your vehicle."
                + ("\n\nQuick response link: $response_link" if response_link else "")
                + "\n\nThanks,\n$business_name"
            ),
        },
    }
    selected = templates.get(template_key, templates["first_follow_up"])
    return {
        "subject": _render_template(selected["subject"], values),
        "body": _render_template(selected["body"], values),
    }


def generate_ai_follow_up_message(
    quote: dict[str, Any],
    business_settings: dict[str, Any],
    tone: str = "friendly",
) -> dict[str, str] | None:
    """Optionally generate a message with OpenAI if OPENAI_API_KEY is configured."""
    cfg = get_settings()
    if not cfg.openai_api_key:
        return None

    prompt = {
        "instruction": "Write a concise follow-up email. Avoid discounts, guarantees, fake scarcity, and unsupported claims.",
        "tone": tone,
        "business": business_settings,
        "quote": quote,
    }
    request = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(
            {
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": "Return JSON with subject and body."},
                    {"role": "user", "content": json.dumps(prompt)},
                ],
                "temperature": 0.4,
            }
        ).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {cfg.openai_api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
            content = payload["choices"][0]["message"]["content"]
            return json.loads(content)
    except Exception:
        return None
