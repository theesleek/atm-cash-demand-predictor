from __future__ import annotations

import argparse
from datetime import date, datetime, timezone

from app.db.session import SessionLocal
from app.jobs.queue import enqueue_daily_forecast_job


def enqueue_today() -> int:
    session = SessionLocal()
    try:
        job = enqueue_daily_forecast_job(session, datetime.now(timezone.utc).date())
        if job is None:
            print("Daily automation is disabled; no job was enqueued.")
            return 0
        print(f"Daily forecast job {job.id} is {job.status} for {job.dedupe_key}.")
        return 0
    finally:
        session.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Enqueue the operator-enabled daily forecast refresh")
    parser.add_argument("--date", type=date.fromisoformat, help="UTC operational date (defaults to today)")
    args = parser.parse_args()
    if args.date is None:
        raise SystemExit(enqueue_today())
    session = SessionLocal()
    try:
        job = enqueue_daily_forecast_job(session, args.date)
        if job is None:
            print("Daily automation is disabled; no job was enqueued.")
        else:
            print(f"Daily forecast job {job.id} is {job.status} for {job.dedupe_key}.")
    finally:
        session.close()


if __name__ == "__main__":
    main()
