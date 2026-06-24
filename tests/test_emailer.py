import json

import emailer


def test_build_resend_request_headers_and_payload():
    request = emailer.build_resend_request(
        api_key="secret",
        from_email="from@example.com",
        to_email="to@example.com",
        subject="Hello",
        body="Body",
        reply_to="owner@example.com",
    )
    payload = json.loads(request.data.decode("utf-8"))
    assert request.headers["Authorization"] == "Bearer secret"
    assert request.headers["Content-type"] == "application/json"
    assert request.headers["Accept"] == "application/json"
    assert request.headers["User-agent"] == "EstimateRescueStreamlit/1.0"
    assert payload["from"] == "from@example.com"
    assert payload["to"] == ["to@example.com"]
    assert payload["subject"] == "Hello"
    assert payload["reply_to"] == "owner@example.com"


def test_missing_email_config_returns_disabled(monkeypatch):
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.delenv("RESEND_FROM_EMAIL", raising=False)
    result = emailer.send_email(to_email="to@example.com", subject="Hi", body="Body")
    assert result["ok"] is False
    assert result["status"] == "email_disabled"
