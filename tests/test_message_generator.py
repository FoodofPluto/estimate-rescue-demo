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


def test_saved_template_renders_settings_sample():
    import message_generator

    rendered = message_generator.render_saved_template(
        {
            "subject_template": "$service_type estimate",
            "body_template": "Hi $customer_name, your estimate is $quote_amount.",
        },
        {
            "customer_name": "Maya",
            "service_type": "Ceramic coating",
            "quote_amount": 1295.0,
            "response_link": "https://example.com/respond",
        },
        {"business_name": "Detail Shop"},
    )
    assert rendered == {
        "subject": "Ceramic coating estimate",
        "body": "Hi Maya, your estimate is $1,295.00.",
    }


def test_saved_template_supports_amount_alias_and_invalid_amount():
    import message_generator

    template = {"subject_template": "$quote_amount", "body_template": "$customer_name"}
    settings = {"business_name": "Detail Shop"}
    assert message_generator.render_saved_template(template, {"amount": "1,200"}, settings)[
        "subject"
    ] == "$1,200.00"
    assert message_generator.render_saved_template(
        template, {"quote_amount": "invalid"}, settings
    )["subject"] == "$0.00"


def test_saved_template_preview_tolerates_missing_and_invalid_placeholders():
    import message_generator

    settings = {"business_name": "Detail Shop"}
    missing = message_generator.render_saved_template(
        {"subject_template": "$customer_name", "body_template": "$unknown_value"}, {}, settings
    )
    assert missing["subject"] == "there"
    assert missing["body"] == "$unknown_value"

    invalid = message_generator.render_saved_template(
        {"subject_template": "$", "body_template": "$quote_amount"},
        {"quote_amount": "$1,200.50"},
        settings,
    )
    assert invalid == {"subject": "$", "body": "$1,200.50"}
