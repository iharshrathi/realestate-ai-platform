"""CLI: load SYNTHETIC demo data into the configured database.

Usage (from ``backend/``):  python -m scripts.seed [--leads 300] [--reset]
"""

from __future__ import annotations

import argparse
import logging

from app.core.config import get_settings
from app.db.base import Base
from app.db.init_db import init_db
from app.db.seed import seed_demo_data
from app.db.session import SessionLocal, engine


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--leads", type=int, default=300, help="number of synthetic leads")
    parser.add_argument(
        "--reset", action="store_true", help="DROP all tables first (development only)"
    )
    parser.add_argument("--no-score", action="store_true", help="skip scoring leads with the model")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if args.reset:
        if get_settings().environment == "production":
            raise SystemExit("Refusing to --reset a production database")
        Base.metadata.drop_all(bind=engine)
    init_db()
    with SessionLocal() as db:
        print(seed_demo_data(db, n_leads=args.leads, score=not args.no_score))


if __name__ == "__main__":
    main()
