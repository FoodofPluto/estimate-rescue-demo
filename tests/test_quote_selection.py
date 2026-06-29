from quote_logic import quote_selector_label


def test_quote_selector_labels_are_customer_first_and_not_numeric_only():
    label = quote_selector_label(
        {"id": 17, "customer_name": "Maya Chen", "quote_amount": 1295, "created_at": "2026-06-20T10:00:00"}
    )
    assert label.startswith("Maya Chen")
    assert "$1,295.00" in label
    assert "Quote #17" in label


def test_duplicate_customer_names_have_distinguishable_quote_labels():
    first = quote_selector_label(
        {"id": 1, "customer_name": "Alex", "quote_amount": 200, "quote_date": "2026-06-01"}
    )
    second = quote_selector_label(
        {"id": 2, "customer_name": "Alex", "quote_amount": 300, "quote_date": "2026-06-02"}
    )
    assert first != second
    assert first.startswith("Alex") and second.startswith("Alex")
