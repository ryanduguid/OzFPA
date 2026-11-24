"""A price, volume and mix bridge with an independently supplied ledger residual."""
import re
from decimal import Decimal

from pyfpa.analysis.pvm import price_volume_mix


def revenue_bridge(rows: list[dict], prior_ledger: str, current_ledger: str) -> dict:
    if any(not isinstance(value, str) or not re.fullmatch(r"-?\d{1,15}(?:\.\d{1,2})?", value) for value in (prior_ledger, current_ledger)):
        raise ValueError("Ledger revenue requires bounded decimal strings with at most 2 places")
    prior, current = Decimal(prior_ledger), Decimal(current_ledger)
    seen = set()
    for row in rows:
        if set(row) != {"service", "prior_units", "current_units", "prior_price", "current_price", "evidence"} or not row["service"] or row["service"] in seen or not row["evidence"]:
            raise ValueError("Unique services and operational evidence are required")
        seen.add(row["service"])
        if any(not isinstance(row[key], str) or not re.fullmatch(r"\d{1,15}(?:\.\d{1,6})?", row[key]) for key in ("prior_price", "current_price", "prior_units", "current_units")):
            raise ValueError("Prices and units require bounded non-negative decimal strings")
    if not rows:
        raise ValueError("Operational evidence is required")
    bridge = price_volume_mix([{"line": row["service"], **{key: row[key] for key in ("prior_units", "current_units", "prior_price", "current_price")}} for row in rows])
    evidence = {row["service"]: row["evidence"] for row in rows}
    observed = current - prior
    return {"observed": str(observed), "volume": str(bridge.volume), "mix": str(bridge.mix), "price": str(bridge.price),
            "residual": str(observed - bridge.total),
            "prior_ledger_difference": str(prior - sum((line["prior"] for line in bridge.lines), Decimal(0))),
            "current_ledger_difference": str(current - sum((line["current"] for line in bridge.lines), Decimal(0))),
            "details": [{"service": line["line"], **{key: str(value) for key, value in line.items() if key != "line"},
                         "evidence": evidence[line["line"]]} for line in bridge.lines],
            "method": bridge.method + " Residual is unexplained, not an inferred cause."}
