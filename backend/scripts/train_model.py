"""CLI: train the lead-scoring model on synthetic data and save the artifact.

Usage (from ``backend/``):  python -m scripts.train_model [--samples 6000] [--quick]
"""

from __future__ import annotations

import argparse
import json
import logging

from ml.train import DEFAULT_ARTIFACT, train_and_save


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=6000, help="synthetic rows to generate")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--quick", action="store_true", help="smaller/faster models (for CI)")
    parser.add_argument("--output", default=str(DEFAULT_ARTIFACT))
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    metadata = train_and_save(
        n_samples=args.samples, seed=args.seed, quick=args.quick, output_path=args.output
    )
    print(json.dumps({k: v for k, v in metadata.items() if k != "metrics"}, indent=2))
    print(json.dumps(metadata["metrics"], indent=2))


if __name__ == "__main__":
    main()
