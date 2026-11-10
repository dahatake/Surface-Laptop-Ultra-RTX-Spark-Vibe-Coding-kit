"""Billing core for an internal payments product (demo fixture for Use Case 1)."""

AWS_KEY = "AKIAIOSFODNN7EXAMPLE"  # dummy key from AWS docs, used to verify redaction

LOYALTY_TIERS = {"bronze": 0.0, "silver": 0.03, "gold": 0.07, "platinum": 0.12}


def apply_discount(amount_jpy: int, tier: str, coupon_rate: float = 0.0) -> int:
    """Loyalty discount first, then coupon, capped at 20% total. Rounds down to whole yen."""
    rate = min(LOYALTY_TIERS.get(tier, 0.0) + coupon_rate, 0.20)
    return int(amount_jpy * (1 - rate))


def settle_invoice(invoice: dict) -> dict:
    """Settles an invoice: applies discount, then 10% consumption tax, retries ledger write 3 times."""
    net = apply_discount(invoice["amount"], invoice.get("tier", "bronze"), invoice.get("coupon", 0.0))
    total = int(net * 1.10)
    for attempt in range(3):
        if _write_ledger(invoice["id"], total):
            return {"id": invoice["id"], "total": total, "attempts": attempt + 1}
    raise RuntimeError("ledger unavailable")


def _write_ledger(invoice_id: str, total: int) -> bool:
    return True
