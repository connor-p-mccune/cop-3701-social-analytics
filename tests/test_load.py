from datetime import datetime
from decimal import Decimal

import pytest

from social_analytics.config import DATA_DIR
from social_analytics.etl import load
from social_analytics.etl.preprocess import CSV_HEADERS


@pytest.mark.parametrize(
    ("column", "value", "expected"),
    [
        ("tweet_id", "1976990550", 1976990550),
        ("reply_to_tweet_id", "", None),
        ("created_at", "2009-06-01 13:05:59", datetime(2009, 6, 1, 13, 5, 59)),
        ("score", "-1.00", Decimal("-1.00")),
        ("tweet_text", "hello", "hello"),
        ("location", "", None),
    ],
)
def test_convert_maps_csv_strings_to_bind_types(column, value, expected):
    assert load.convert(column, value) == expected


def test_read_rows_rejects_unexpected_headers(tmp_path):
    path = tmp_path / "hashtag.csv"
    path.write_text("id,tag\n1,fb\n", encoding="utf-8")
    with pytest.raises(ValueError, match="expected columns"):
        load.read_rows(path, CSV_HEADERS["hashtag"])


def test_load_order_puts_parents_before_children():
    order = load.LOAD_ORDER
    assert order.index("app_user") < order.index("tweet")
    assert order.index("hashtag") < order.index("tweet_hashtag")
    assert order.index("tweet") < order.index("sentiment_score")
    assert order.index("tweet") < order.index("tweet_hashtag")


def test_committed_dataset_is_consistent():
    """The CSVs in data/ satisfy the schema's keys before they ever reach Oracle."""
    tables = {name: load.read_rows(DATA_DIR / f"{name}.csv", h) for name, h in CSV_HEADERS.items()}
    users = {row[0] for row in tables["app_user"]}
    tweets = {row[0] for row in tables["tweet"]}
    hashtags = {row[0] for row in tables["hashtag"]}

    assert len(users) == len(tables["app_user"])
    assert len(tweets) == len(tables["tweet"])
    assert len({row[1].lower() for row in tables["app_user"]}) == len(users)
    assert all(row[1] in users for row in tables["tweet"])
    assert {row[0] for row in tables["sentiment_score"]} == tweets
    assert all(-1 <= row[1] <= 1 for row in tables["sentiment_score"])
    assert all(row[0] in tweets and row[1] in hashtags for row in tables["tweet_hashtag"])
    assert all(row[1] == row[1].lower() for row in tables["hashtag"])
    assert all(len(row[2]) <= 280 for row in tables["tweet"])
