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
