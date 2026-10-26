import hashlib, re
from collections import defaultdict
from datetime import date
from decimal import Decimal

CATEGORY_RULES = {
    "Groceries": ["grocery", "supermarket", "whole foods", "trader joe", "bigbasket", "blinkit", "zepto", "dmart"],
    "Dining": ["restaurant", "cafe", "coffee", "swiggy", "zomato", "pizza", "burger", "dominos", "starbucks"],
    "Transport": ["uber", "ola", "lyft", "metro", "fuel", "petrol", "shell", "parking", "rapido"],
    "Shopping": ["amazon", "flipkart", "myntra", "store", "retail", "mall"],
    "Bills & Utilities": ["electricity", "water bill", "internet", "broadband", "airtel", "jio", "utility"],
    "Entertainment": ["netflix", "spotify", "prime video", "disney", "youtube premium", "steam", "playstation"],
    "Health": ["pharmacy", "hospital", "clinic", "medical", "apollo", "medicine"],
    "Travel": ["hotel", "airlines", "flight", "booking.com", "makemytrip", "irctc", "airbnb"],
    "Income": ["salary", "payroll", "interest credit", "refund", "cashback", "deposit"],
}
SUBSCRIPTION_HINTS = ["netflix", "spotify", "prime", "youtube premium", "disney", "adobe", "icloud", "google one", "membership", "subscription", "gym", "microsoft 365", "dropbox"]

def normalize_merchant(description: str) -> str:
    text = re.sub(r"\b(UPI|POS|CARD|DEBIT|CREDIT|TXN|REF|ID|NO)\b", " ", description, flags=re.I)
    text = re.sub(r"\d{4,}", " ", text)
    text = re.sub(r"[^A-Za-z0-9 &'.-]", " ", text)
    words = text.split()
    return " ".join(words[:5]).strip(" -")[:200] or "Unknown"

def categorize(description: str, amount: Decimal) -> str:
    lower = description.lower()
    if amount < 0:
        return "Income"
    for category, keywords in CATEGORY_RULES.items():
        if category == "Income":
            continue
        if any(k in lower for k in keywords):
            return category
    return "Uncategorized"

def fingerprint(tx_date: date, description: str, amount: Decimal, account: str) -> str:
    normalized_description = re.sub(r"\s+", " ", description.lower()).strip()
    canonical = f"{tx_date.isoformat()}|{normalized_description}|{amount:.2f}|{account.lower().strip()}"
    return hashlib.sha256(canonical.encode()).hexdigest()

def is_subscription_merchant(merchant: str) -> bool:
    m = merchant.lower()
    return any(hint in m for hint in SUBSCRIPTION_HINTS)
