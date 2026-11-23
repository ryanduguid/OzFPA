"""Tie every figure in the Lumbridge briefing to its source; exit 1 on any it cannot tie.

Each figure is compared with exactly one source: a schedule in the output
folder (`monthly.csv`, `results.json`, `cash-bands.csv`, `debtor-lateness.csv`,
`pull-forward.csv`), an input file under `data/`, or, for the on-time and
45-day late cases the comparison table sets side by side and the delay limits,
the example's own forecast. Any number no tie covers is reported as untied.

    python examples/lumbridge-services/models/generated/verify_briefing.py [--output DIR] [--data DIR]
"""
from __future__ import annotations

import argparse
import json
import runpy
import sys
from functools import cache
from pathlib import Path

import pandas as pd

from pyfpa.analysis.figures import FigureTie, figure_problems

ROOT = Path(__file__).resolve().parents[2]
MONEY = r"\(?\$-?[\d,]+(?:\.\d{2})?\)?"


def _day_month(stamp: pd.Timestamp) -> str:
    return f"{stamp.day} {stamp.strftime('%B')}"


@cache
def _generator() -> dict:
    return runpy.run_path(str(Path(__file__).with_name("lumbridge.py")))


@cache
def sources(output: Path = ROOT / "output", data: Path = ROOT / "data") -> dict:
    generator = _generator()
    late_days = generator["LATE_CASE_DAYS"]
    invoices = pd.read_csv(data / "invoices.csv", parse_dates=["receipt_date"]).set_index("id")
    assumptions = json.loads((data / "assumptions.json").read_text(encoding="utf-8"))
    on_time, late = generator["forecast"](data), generator["forecast"](data, delay_days=late_days)
    pl = pd.read_csv(data / "xero_pl.csv")
    return {
        "late_days": late_days,
        "monthly": pd.read_csv(output / "monthly.csv", index_col=0),
        "results": json.loads((output / "results.json").read_text(encoding="utf-8")),
        "lateness": pd.read_csv(output / "debtor-lateness.csv"),
        "levers": pd.read_csv(output / "pull-forward.csv"),
        "band_paths": pd.read_csv(output / "cash-bands.csv", index_col="week"),
        "assumptions": assumptions,
        "bands_settings": json.loads((data / "cash-bands.json").read_text(encoding="utf-8")),
        "opening": pd.read_csv(data / "xero_bs.csv").set_index("Account")["Amount"],
        "delayed": invoices.loc[assumptions["delay_invoice"]],
        "on_time_monthly": on_time["monthly"],
        "on_time_daily": on_time["daily"]["ending_cash"],
        "late_monthly": late["monthly"],
        "late_daily": late["daily"]["ending_cash"],
        "flip_points": generator["flip_points"](data),
        "september_revenue": pl.loc[pl["Account"].str.startswith("Sales"), "Amount"].sum(),
    }


def _ranges(delays: list[dict]) -> str:
    def ids(names: list[str]) -> str:
        return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"
    return "; ".join(f"{ids(rule['ids'])} {rule['low_days']} to {rule['high_days']} days late" for rule in delays)


def briefing_ties(output: Path = ROOT / "output", data: Path = ROOT / "data") -> list[FigureTie]:
    s = sources(output, data)
    m, lm, r, a = s["monthly"], s["late_monthly"], s["results"], s["assumptions"]
    late_daily, late_days, bands = s["late_daily"], s["late_days"], r["cash_floor_bands"]
    months = pd.PeriodIndex(m.index, freq="M")
    trough = -late_daily.min()
    lateness = s["lateness"]
    open_v = s["levers"][s["levers"]["debtor"] == a["delay_invoice"]].sort_values("days_sooner")
    om = s["on_time_monthly"]
    comparison = {
        "Quarter revenue": (om["Revenue"].sum(), lm["Revenue"].sum()),
        "Quarter profit before tax": (om["Profit before tax"].sum(), lm["Profit before tax"].sum()),
        "October closing cash": (om["Closing cash"].iloc[0], lm["Closing cash"].iloc[0]),
        "Minimum daily cash": (s["on_time_daily"].min(), late_daily.min()),
        "December closing cash": (om["Closing cash"].iloc[-1], lm["Closing cash"].iloc[-1]),
    }
    return [
        FigureTie("period", r"business\. (\w+) to (\w+) (\d{4}), AUD\.",
                  (months[0].strftime("%B"), months[-1].strftime("%B"), months[-1].year)),
        FigureTie("late case heading", r"\| OPEN-V paid (\d+) days late \|", (late_days,)),
        *[FigureTie(f"comparison row {label!r}", rf"^\| {label} \| ({MONEY}) \| ({MONEY}) \|$", pair)
          for label, pair in comparison.items()],
        *[FigureTie(f"monthly review row {month}", rf"^\| {month} \| ({MONEY}) \| ({MONEY}) \| ({MONEY}) \|$",
                    (row["Revenue"], row["Profit before tax"], row["Closing cash"])) for month, row in m.iterrows()],
        FigureTie("base-case profit", rf"The base case earns ({MONEY}) before income tax", (om["Profit before tax"].sum(),)),
        FigureTie("table delay", r"This monthly table uses a (\d+)-day receipt delay", (r["delay_days"],)),
        FigureTie("opening GST", rf"October includes ({MONEY}) of opening GST", (-s["opening"]["GST"],)),
        FigureTie("October instalment", rf"and a ({MONEY}) income tax instalment", (m["Income tax instalment"].iloc[0],)),
        FigureTie("first overdrawn day", r"The late case first becomes negative on (\d{1,2} \w+)",
                  (_day_month(late_daily[late_daily < 0].index[0]),)),
        FigureTie("trough", rf"reaches ({MONEY}) on (\d{{1,2}} \w+)", (late_daily.min(), _day_month(late_daily.idxmin()))),
        FigureTie("delayed receipt date", r"the delayed receipt arrives on (\d{1,2} \w+)",
                  (_day_month(s["delayed"]["receipt_date"] + pd.Timedelta(days=late_days)),)),
        FigureTie("December payables",
                  rf"At (\d{{1,2}} \w+), ({MONEY}) GST, ({MONEY}) PAYG withholding and ({MONEY}) supplier invoices remain payable",
                  (_day_month(months[-1].end_time), m["GST payable"].iloc[-1], m["PAYG withholding payable"].iloc[-1],
                   m["Supplier payables"].iloc[-1])),
        FigureTie("loan balance", rf"The loan balance is ({MONEY})", (-s["opening"]["Business Loan"] - m["Loan principal paid"].sum(),)),
        FigureTie("leave provisions", rf"the quarter adds ({MONEY}) of unused leave provisions", (m["Leave provision"].sum(),)),
        FigureTie("delayed receipt", rf"Confirm the ({MONEY}) OPEN-V receipt date", (s["delayed"]["net"] + s["delayed"]["gst"],)),
        FigureTie("delay limits",
                  rf"stays at or above zero if OPEN-V is up to (\d+) days late and stays at or above the assumed ({MONEY}) buffer "
                  r"if OPEN-V is up to (\d+) days late",
                  (s["flip_points"]["zero"], a["minimum_cash_buffer"], s["flip_points"]["buffer"])),
        FigureTie("trough funding", rf"The (\d+)-day delay needs ({MONEY}) of additional cash at the trough", (late_days, trough)),
        FigureTie("buffer funding", rf"or ({MONEY}) to preserve the assumed ({MONEY}) buffer",
                  (trough + a["minimum_cash_buffer"], a["minimum_cash_buffer"])),
        FigureTie("past-due invoices", r"In the (\d+)-day late case, (\d+) of (\d+) invoices (?:is|are) past due",
                  (late_days, lateness.loc[lateness["late_amount"] > 0, "invoices"].sum(), lateness["invoices"].sum())),
        FigureTie("pull-forward levers",
                  rf"if ({a['delay_invoice']}) were received sooner, lowest daily cash would move from ({MONEY}): "
                  rf"(\d+) days sooner to ({MONEY}), (\d+) days sooner to ({MONEY}), (\d+) days sooner to ({MONEY})\.",
                  (a["delay_invoice"], late_daily.min(),
                   *[value for row in open_v.itertuples() for value in (row.days_sooner, row.floor_after)])),
        FigureTie("band runs and seed", r"In ([\d,]+) seeded runs \(seed (\d+)\)", (bands["runs"], bands["seed"])),
        FigureTie("band ranges", r"each day in its range equally likely: ([^.]+)\. Payments keep their dates",
                  (_ranges(s["bands_settings"]["delays"]),)),
        FigureTie("band floors", rf"Lowest daily cash is ({MONEY}) at P10, ({MONEY}) at P50 and ({MONEY}) at P90",
                  tuple(bands["floor"][p] for p in ("p10", "p50", "p90"))),
        FigureTie("band breaches", rf"([\d,]+) runs go below zero and ([\d,]+) below the ({MONEY}) buffer",
                  (bands["runs_below_zero"], bands["runs_below_buffer"], a["minimum_cash_buffer"])),
        FigureTie("band paths", r"`cash-bands\.csv` gives the (\d+) paths week by week",
                  (len([column for column in s["band_paths"].columns if column.startswith("p")]),)),
        FigureTie("run-rate revenue", rf"held at September's fabricated ({MONEY}) monthly run rate", (s["september_revenue"],)),
        FigureTie("run-rate profit", rf"monthly pre-tax profit remains ({MONEY})", (m["Profit before tax"].iloc[0],)),
    ]


def briefing_problems(text: str, output: Path = ROOT / "output", data: Path = ROOT / "data") -> list[str]:
    return figure_problems(text, briefing_ties(output, data))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "output")
    parser.add_argument("--data", type=Path, default=ROOT / "data")
    args = parser.parse_args(argv)
    briefing = args.output / "briefing.md"
    problems = briefing_problems(briefing.read_text(encoding="utf-8"), args.output, args.data)
    print(json.dumps({"briefing": str(briefing), "problems": problems}, indent=2))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
