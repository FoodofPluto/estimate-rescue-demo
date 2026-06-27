import importlib
import os


def test_message_includes_customer_service_and_business(monkeypatch):
    monkeypatch.setenv("APP_BASE_URL", "https://demo.example")
    import config
    import message_generator

    importlib.reload(config)
    importlib.reload(message_generator)
    quote = {
        "customer_name": "Maya",
        "service_type": "Ceramic coating",
        "quote_amount": 1295,
        "public_response_token": "abc123",
    }
    settings = {"business_name": "Blue Ridge Auto Detail"}
    message = message_generator.generate_follow_up_message(quote, settings)
    combined = message["subject"] + message["body"]
    assert "Maya" in combined
    assert "Ceramic coating" in combined
    assert "Blue Ridge Auto Detail" in combined
    assert "https://demo.example" in combined
    assert "token=abc123" in combined


def test_response_link_contains_persisted_token(monkeypatch):
    monkeypatch.setenv("APP_BASE_URL", "https://demo.example/base/")
    import config
    import message_generator

    importlib.reload(config)
    importlib.reload(message_generator)
    link = message_generator.response_link_for_quote({"public_response_token": "stable-token"})
    assert link == "https://demo.example/base/?page=Customer+Response+Page&token=stable-token"


def test_template_values_are_safe_without_response_link(monkeypatch):
    monkeypatch.delenv("APP_BASE_URL", raising=False)
    import config
    import message_generator

    importlib.reload(config)
    importlib.reload(message_generator)
    values = message_generator.template_values(
        {"customer_name": "Jordan", "service_type": "Interior detail", "quote_amount": 250},
        {"business_name": "Blue Ridge Auto Detail"},
    )
    assert values["customer_name"] == "Jordan"
    assert values["service_type"] == "Interior detail"
    assert values["quote_amount"] == "$250.00"
    assert values["response_link"] == ""


def test_edited_persisted_template_changes_generated_output(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "templates.db"))
    monkeypatch.setenv("APP_BASE_URL", "https://demo.example")
    import config
    import message_generator
    import storage

    importlib.reload(config)
    importlib.reload(storage)
    importlib.reload(message_generator)
    storage.init_db()
    storage.upsert_message_template(
        "custom", "Custom", "Estimate for $customer_name", "Use $response_link for $service_type."
    )
    saved = next(item for item in storage.list_message_templates() if item["template_key"] == "custom")
    rendered = message_generator.render_saved_template(
        saved,
        {
            "customer_name": "Taylor",
            "service_type": "Paint correction",
            "quote_amount": 500,
            "public_response_token": "persisted-token",
        },
        {"business_name": "Detail Shop"},
    )
    assert rendered["subject"] == "Estimate for Taylor"
    assert "token=persisted-token" in rendered["body"]
