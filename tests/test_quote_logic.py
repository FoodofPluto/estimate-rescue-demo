from quote_logic import calculate_recovery_score, default_follow_up_due_date, format_currency, normalize_status


def test_recovery_score_range():
    score = calculate_recovery_score(
        {
            "quote_amount": 750,
            "quote_date": "2026-01-01",
            "follow_up_due_date": "2026-01-02",
            "status": "follow_up_due",
            "follow_up_count": 1,
        }
    )
    assert 0 <= score <= 100


def test_helpers():
    assert normalize_status("bad") == "new_quote"
    assert default_follow_up_due_date("2026-01-01") == "2026-01-03"
    assert format_currency(1234) == "$1,234.00"
