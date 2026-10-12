"""Interactive terminal menu for the query catalog.

The menu design and the original five features were written by Johnathan
Nguyen. This version runs every query from sql/queries.sql, validates input
instead of crashing on it, keeps one connection for the session, and adds
the trend analytics (Features 6-9).

Usage:
    python -m social_analytics cli
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal

import oracledb

from . import queries
from .db import connect, fetch

MAX_ROWS = 50
MAX_TEXT_WIDTH = 70


# --------------------------------------------------------------------------
# Input
# --------------------------------------------------------------------------


def ask(prompt: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default is not None else ""
    while True:
        value = input(f"{prompt}{suffix}: ").strip()
        if value:
            return value
        if default is not None:
            return default
        print("  A value is required.")


def ask_int(prompt: str, default: int | None = None, minimum: int = 1) -> int:
    while True:
        value = ask(prompt, None if default is None else str(default))
        try:
            number = int(value)
        except ValueError:
            print("  Please enter a whole number.")
            continue
        if number >= minimum:
            return number
        print(f"  Please enter a number of at least {minimum}.")


def ask_date(prompt: str, default: str | None = None) -> str:
    while True:
        value = ask(f"{prompt} (YYYY-MM-DD)", default)
        try:
            date.fromisoformat(value)
        except ValueError:
            print("  Please enter a date like 2009-06-01.")
            continue
        return value


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------


def decimal_places(values: list[object]) -> int | None:
    """Fewest decimal places (at most 4) that show every number in a column.

    Returns None for columns without fractional numbers. The driver returns
    whole-number values as int, so 1 and -0.7059 can share a column.
    """
    fractions = [
        f"{value:.4f}".rstrip("0").split(".")[1]
        for value in values
        if isinstance(value, float | Decimal)
    ]
    return max(map(len, fractions)) if fractions else None


def format_value(value: object, places: int | None = None) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        is_midnight = value.time() == datetime.min.time()
        return value.strftime("%Y-%m-%d" if is_midnight else "%Y-%m-%d %H:%M")
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int | float | Decimal) and places is not None:
        return f"{value:,.{places}f}"
    if isinstance(value, int):
        return f"{value:,}" if abs(value) < 10**9 else str(value)  # keep ids unformatted
    text = " ".join(str(value).split())
    return text if len(text) <= MAX_TEXT_WIDTH else text[: MAX_TEXT_WIDTH - 1] + "…"


def print_table(columns: list[str], rows: list[tuple]) -> None:
    if not rows:
        print("\nNo results found.\n")
        return

    shown = rows[:MAX_ROWS]
    places = [decimal_places([row[i] for row in shown]) for i in range(len(columns))]
    cells = [[format_value(v, places[i]) for i, v in enumerate(row)] for row in shown]
    numeric = [
        all(isinstance(row[i], int | float | Decimal) or row[i] is None for row in shown)
        for i in range(len(columns))
    ]
    widths = [max(len(col), *(len(r[i]) for r in cells)) for i, col in enumerate(columns)]

    def line(values: list[str]) -> str:
        return "  ".join(
            v.rjust(w) if is_num else v.ljust(w)
            for v, w, is_num in zip(values, widths, numeric, strict=True)
        ).rstrip()

    print()
    print(line(columns))
    print(line(["-" * w for w in widths]))
    for row in cells:
        print(line(row))
    more = f" (showing first {MAX_ROWS})" if len(rows) > MAX_ROWS else ""
    print(f"\n{len(rows):,} row{'s' if len(rows) != 1 else ''}{more}\n")


# --------------------------------------------------------------------------
# Menu
# --------------------------------------------------------------------------

Prompt = Callable[[], dict[str, object]]

MENU: dict[str, tuple[str, str, Prompt]] = {
    "1": ("View all tweets by a user", "tweets_by_user", lambda: {"username": ask("Username")}),
    "2": (
        "View all hashtags used in a tweet",
        "hashtags_for_tweet",
        lambda: {"tweet_id": ask_int("Tweet ID")},
    ),
    "3": (
        "Find all tweets with a hashtag",
        "tweets_with_hashtag",
        lambda: {"hashtag": ask("Hashtag", "followfriday")},
    ),
    "4": (
        "View tweet sentiment scores in a date range",
        "sentiment_in_date_range",
        lambda: {
            "start_date": ask_date("Start date", "2009-06-01"),
            "end_date": ask_date("End date", "2009-06-01"),
        },
    ),
    "5": (
        "Show the top hashtags by usage",
        "top_hashtags",
        lambda: {"row_limit": ask_int("How many", 10)},
    ),
    "6": (
        "Show each day's top hashtags in a date range",
        "daily_top_hashtags",
        lambda: {
            "start_date": ask_date("Start date", "2009-05-29"),
            "end_date": ask_date("End date", "2009-06-01"),
            "top_n": ask_int("Hashtags per day", 3),
        },
    ),
    "7": (
        "Show the daily sentiment trend for a hashtag",
        "hashtag_daily_trend",
        lambda: {"hashtag": ask("Hashtag", "followfriday")},
    ),
    "8": (
        "Show the most positive and negative hashtags in a date range",
        "hashtag_sentiment_extremes",
        lambda: {
            "start_date": ask_date("Start date", "2009-05-25"),
            "end_date": ask_date("End date", "2009-06-07"),
            "min_tweets": ask_int("Minimum tweets per hashtag", 10),
            "top_n": ask_int("How many of each", 5),
        },
    ),
    "9": (
        "Show trending hashtags for a week",
        "trending_hashtags",
        lambda: {
            "week_of": ask_date("Any date in the week", "2009-06-01"),
            "top_n": ask_int("How many", 10),
        },
    ),
}


def print_header(conn: oracledb.Connection) -> None:
    _, [overview] = fetch(conn, queries.get("dataset_overview").sql)
    tweets, users, hashtags, _links, pct_positive, first_day, last_day = overview
    print(
        f"\nTweet Analytics — {tweets:,} tweets, {users:,} users, {hashtags:,} hashtags, "
        f"{pct_positive}% positive, {first_day:%Y-%m-%d} to {last_day:%Y-%m-%d}"
    )


def run_menu(conn: oracledb.Connection) -> None:
    print_header(conn)
    while True:
        print()
        for key, (label, _query, _prompt) in MENU.items():
            print(f"{key}. {label}")
        print("0. Exit")

        choice = input("Choose an option: ").strip()
        if choice == "0":
            print("Goodbye.")
            return
        if choice not in MENU:
            print("Invalid choice. Please try again.")
            continue

        _label, query_name, prompt = MENU[choice]
        params = prompt()
        try:
            print_table(*fetch(conn, queries.get(query_name).sql, params))
        except oracledb.DatabaseError as error:
            print(f"\nQuery failed: {error}\n")


def main(argv: list[str] | None = None) -> None:
    argparse.ArgumentParser(
        prog="python -m social_analytics cli",
        description="Interactive menu for exploring the tweet analytics database.",
    ).parse_args(argv)
    try:
        conn = connect()
    except (oracledb.Error, RuntimeError) as error:
        sys.exit(
            f"Could not connect to the database: {error}\n"
            "Is it running (docker compose up -d) and configured in .env?"
        )
    with conn:
        try:
            run_menu(conn)
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")


if __name__ == "__main__":
    main()
