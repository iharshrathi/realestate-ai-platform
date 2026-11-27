"""CLI: write the synthetic training dataset to CSV (for inspection / use outside the API).

Usage (from ``backend/``):  python -m scripts.generate_data --rows 1000 --output ../data/synthetic_leads.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

from ml.synthetic_data import generate_leads


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", default="../data/synthetic_leads.csv")
    args = parser.parse_args()

    frame = generate_leads(args.rows, seed=args.seed)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output, index=False)
    print(
        f"Wrote {len(frame)} SYNTHETIC rows to {output} (conversion rate {frame.converted.mean():.1%})"
    )


if __name__ == "__main__":
    main()
