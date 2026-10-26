from datetime import date
from decimal import Decimal
from app.logic import categorize, normalize_merchant, fingerprint

def test_categories_are_explainable():
    assert categorize("NETFLIX.COM monthly plan", Decimal("499")) == "Entertainment"
    assert categorize("Salary credit", Decimal("-45000")) == "Income"
    assert categorize("Unknown merchant", Decimal("250")) == "Uncategorized"

def test_fingerprint_is_stable():
    assert fingerprint(date(2026, 1, 2), "ABC   STORE", Decimal("125.00"), "Main") == fingerprint(date(2026, 1, 2), "abc store", Decimal("125.00"), "main")

def test_merchant_normalization():
    assert normalize_merchant("UPI/NETFLIX/123456789") != ""
