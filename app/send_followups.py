"""Entrypoint for a scheduled run: `python -m app.send_followups`."""

from . import db, messaging


def main() -> None:
    db.init_db()
    result = messaging.send_daily_followups()
    print(result)


if __name__ == "__main__":
    main()
