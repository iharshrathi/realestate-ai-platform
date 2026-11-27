"""CLI: exploratory analysis of the synthetic lead dataset -> Markdown report.

Usage (from ``backend/``):  python -m scripts.run_eda [--rows 6000] [--output ../docs/eda_report.md]
Everything analysed here is SYNTHETIC; the relationships are the ones the generator was told to create.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from ml.synthetic_data import generate_leads


def _table(frame: pd.DataFrame) -> str:
    """Render a small DataFrame as a Markdown table (no extra dependency needed)."""
    header = "| " + " | ".join(str(c) for c in frame.columns) + " |"
    divider = "| " + " | ".join("---" for _ in frame.columns) + " |"
    rows = ["| " + " | ".join(str(v) for v in row) + " |" for row in frame.itertuples(index=False)]
    return "\n".join([header, divider, *rows])


def _rate_by(df: pd.DataFrame, column: str) -> pd.DataFrame:
    grouped = df.groupby(column, observed=True)["converted"].agg(
        leads="size", conversion_rate="mean"
    )
    grouped["conversion_rate"] = (grouped["conversion_rate"] * 100).round(1).astype(str) + "%"
    return grouped.reset_index()


def build_report(df: pd.DataFrame) -> str:
    sections = [
        "# Exploratory data analysis (synthetic data)",
        "> **All figures below describe generated data, not real customers.** The patterns exist because "
        "the generator in `backend/ml/synthetic_data.py` was written to produce them.",
        f"Rows: **{len(df):,}** · overall conversion rate: **{df['converted'].mean():.1%}**",
        "## Missing values\n"
        + _table(
            df.isna()
            .sum()
            .rename("missing")
            .reset_index()
            .rename(columns={"index": "column"})
            .query("missing > 0")
            if df.isna().any().any()
            else pd.DataFrame({"column": ["(none)"], "missing": [0]})
        ),
        "## Conversion by source\n" + _table(_rate_by(df, "source")),
        "## Conversion by property type\n" + _table(_rate_by(df, "property_type")),
        "## Conversion by number of site visits\n"
        + _table(_rate_by(df.assign(site_visits=df["site_visits"].clip(upper=3)), "site_visits")),
        "## Conversion by loan pre-approval\n" + _table(_rate_by(df, "loan_preapproved")),
        "## Conversion by purchase timeline\n"
        + _table(
            _rate_by(
                df.assign(
                    timeline=pd.cut(
                        df["purchase_timeline_days"],
                        [0, 30, 90, 180, 3650],
                        labels=["≤30d", "31-90d", "91-180d", ">180d"],
                    )
                    .astype(object)
                    .fillna("not stated")
                ),
                "timeline",
            )
        ),
        "## Numeric summary\n"
        + _table(
            df.select_dtypes("number")
            .describe()
            .T.round(2)[["mean", "std", "min", "50%", "max"]]
            .reset_index()
            .rename(columns={"index": "feature"})
        ),
        "## Correlation with conversion\n"
        + _table(
            df.select_dtypes("number")
            .corr()["converted"]
            .drop("converted")
            .sort_values(key=abs, ascending=False)
            .round(3)
            .rename("correlation")
            .reset_index()
            .rename(columns={"index": "feature"})
        ),
        '## Caveats\n- Correlation is not causation, and here the "causes" were put in by hand.\n'
        "- Real CRM data will have different distributions, label noise and leakage risks; re-run this "
        "analysis and re-validate the model before trusting any score.",
    ]
    return "\n\n".join(sections) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=6000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", default="../docs/eda_report.md")
    args = parser.parse_args()

    report = build_report(generate_leads(args.rows, seed=args.seed))
    Path(args.output).write_text(report, encoding="utf-8")
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
