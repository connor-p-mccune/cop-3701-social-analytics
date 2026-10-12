"""End-to-end checks against a real Oracle database: pytest -m integration"""

import csv
from datetime import datetime

import oracledb
import pytest

from social_analytics import queries
from social_analytics.config import DATA_DIR
from social_analytics.db import fetch
from social_analytics.etl.preprocess import CSV_HEADERS

pytestmark = pytest.mark.integration

RANGE = {"start_date": "2009-05-25", "end_date": "2009-06-07"}

# Sample parameters for every query in the catalog. A new query must be
# added here, which keeps the integration suite exhaustive.
QUERY_PARAMS = {
    "tweets_by_user": {"username": "@ThisGoesHere"},
    "hashtags_for_tweet": {"tweet_id": 1976990550},
    "tweets_with_hashtag": {"hashtag": "#E3"},
    "sentiment_in_date_range": {"start_date": "2009-06-16", "end_date": "2009-06-16"},
    "top_hashtags": {"row_limit": 5},
    "daily_top_hashtags": {**RANGE, "top_n": 3},
    "hashtag_daily_trend": {"hashtag": "followfriday"},
    "hashtag_sentiment_extremes": {**RANGE, "min_tweets": 10, "top_n": 5},
    "trending_hashtags": {"week_of": "2009-06-01", "top_n": 10},
    "dataset_overview": {},
    "period_summary": RANGE,
    "daily_activity": RANGE,
    "top_hashtags_in_range": {**RANGE, "row_limit": 10},
    "popular_hashtags": {"min_tweets": 25},
    "hashtag_period_summary": {"hashtag": "followfriday", **RANGE},
}


def run(conn, name, **overrides):
    return fetch(conn, queries.get(name).sql, {**QUERY_PARAMS[name], **overrides})


def scalar(conn, sql, params=None):
    return fetch(conn, sql, params)[1][0][0]


# --------------------------------------------------------------------------
# Load and rollups
# --------------------------------------------------------------------------


def test_every_table_matches_its_csv(conn):
    for name in CSV_HEADERS:
        with (DATA_DIR / f"{name}.csv").open(encoding="utf-8") as fh:
            expected = sum(1 for _ in csv.reader(fh)) - 1
        assert scalar(conn, f"SELECT COUNT(*) FROM {name}") == expected, name


def test_rollup_accounts_for_every_hashtag_link(conn):
    links = scalar(conn, "SELECT COUNT(*) FROM tweet_hashtag")
    assert scalar(conn, "SELECT SUM(tweet_count) FROM hashtag_daily_stats") == links


def test_refresh_is_idempotent(conn):
    snapshot = "SELECT * FROM hashtag_daily_stats ORDER BY hashtag_id, stat_date"
    before = fetch(conn, snapshot)[1]
    with conn.cursor() as cursor:
        cursor.callproc("refresh_hashtag_stats")
    assert fetch(conn, snapshot)[1] == before  # refreshed_at included: no row was touched
    conn.rollback()


def test_windowed_refresh_tracks_deleted_tweets(conn):
    day = datetime(2009, 6, 1)
    count_sql = """
        SELECT d.tweet_count FROM hashtag_daily_stats d JOIN hashtag h USING (hashtag_id)
         WHERE h.tag_text = 'e3' AND d.stat_date = :day"""
    before = scalar(conn, count_sql, {"day": day})
    with conn.cursor() as cursor:
        cursor.execute(
            """DELETE FROM tweet WHERE tweet_id = (
                   SELECT MIN(th.tweet_id) FROM tweet_hashtag th
                     JOIN hashtag h USING (hashtag_id)
                     JOIN tweet t ON t.tweet_id = th.tweet_id
                    WHERE h.tag_text = 'e3' AND TRUNC(t.created_at) = :day)""",
            {"day": day},
        )
        cursor.callproc("refresh_hashtag_stats", [day, day])
    assert scalar(conn, count_sql, {"day": day}) == before - 1
    conn.rollback()


# --------------------------------------------------------------------------
# Constraints
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("statement", "error_code"),
    [
        # A username differing only in case violates the case-insensitive unique index.
        (
            "INSERT INTO app_user SELECT 999999, UPPER(username), 'x@example.com', NULL, "
            "NULL, SYSTIMESTAMP FROM app_user WHERE user_id = 1",
            1,
        ),
        ("UPDATE hashtag SET tag_text = 'FollowFriday' WHERE tag_text = 'followfriday'", 2290),
        ("UPDATE sentiment_score SET score = 2 WHERE ROWNUM = 1", 2290),
        ("UPDATE tweet SET reply_to_tweet_id = tweet_id WHERE ROWNUM = 1", 2290),
        ("INSERT INTO tweet_hashtag VALUES (1, 1, SYSTIMESTAMP)", 2291),
    ],
)
def test_constraints_reject_invalid_rows(conn, statement, error_code):
    with pytest.raises(oracledb.DatabaseError) as excinfo, conn.cursor() as cursor:
        cursor.execute(statement)
    assert excinfo.value.args[0].code == error_code
    conn.rollback()


def test_deleting_a_tweet_cascades_to_its_score_and_links(conn):
    tweet_id = QUERY_PARAMS["hashtags_for_tweet"]["tweet_id"]
    with conn.cursor() as cursor:
        cursor.execute("DELETE FROM tweet WHERE tweet_id = :id", {"id": tweet_id})
    for table in ("sentiment_score", "tweet_hashtag"):
        assert (
            scalar(conn, f"SELECT COUNT(*) FROM {table} WHERE tweet_id = :id", {"id": tweet_id})
            == 0
        )
    conn.rollback()


# --------------------------------------------------------------------------
# Query catalog
# --------------------------------------------------------------------------


def test_integration_suite_covers_the_whole_catalog():
    assert set(QUERY_PARAMS) == set(queries.catalog())


@pytest.mark.parametrize("name", sorted(QUERY_PARAMS))
def test_every_catalog_query_runs_and_returns_rows(conn, name):
    assert set(queries.get(name).binds) == set(QUERY_PARAMS[name])
    columns, rows = run(conn, name)
    assert columns
    assert rows, f"{name} returned no rows for its sample parameters"


def test_username_lookup_ignores_case_and_at_sign(conn):
    _, upper = run(conn, "tweets_by_user", username="@THISGOESHERE")
    _, lower = run(conn, "tweets_by_user", username="thisgoeshere")
    assert upper == lower
    assert len(upper) > 1


def test_date_range_end_includes_the_whole_last_day(conn):
    _, rows = run(conn, "sentiment_in_date_range")
    _, [day] = fetch(
        conn,
        "SELECT tweet_count FROM v_daily_activity WHERE activity_date = DATE '2009-06-16'",
    )
    assert len(rows) == day[0]


def test_top_hashtags_respects_its_limit(conn):
    columns, rows = run(conn, "top_hashtags", row_limit=3)
    assert len(rows) == 3
    assert rows[0][0] == "followfriday"


def test_trending_week_of_e3_expo(conn):
    columns, rows = run(conn, "trending_hashtags")
    top = dict(zip(columns, rows[0], strict=True))
    assert top["tag_text"] == "e3"
    assert top["prev_week_uses"] == 0
    assert top["growth_pct"] is None


def test_sentiment_extremes_are_ordered_on_each_side(conn):
    columns, rows = run(conn, "hashtag_sentiment_extremes")
    records = [dict(zip(columns, row, strict=True)) for row in rows]
    positive = [r["net_sentiment"] for r in records if r["side"] == "positive"]
    negative = [r["net_sentiment"] for r in records if r["side"] == "negative"]
    assert positive == sorted(positive, reverse=True)
    assert negative == sorted(negative)
    min_tweets = QUERY_PARAMS["hashtag_sentiment_extremes"]["min_tweets"]
    assert all(r["tweet_count"] >= min_tweets for r in records)


def test_username_lookup_uses_the_case_insensitive_index(conn):
    with conn.cursor() as cursor:
        cursor.execute("EXPLAIN PLAN FOR " + queries.get("tweets_by_user").sql, {"username": "x"})
    plan = "\n".join(
        row[0]
        for row in fetch(conn, "SELECT plan_table_output FROM TABLE(DBMS_XPLAN.DISPLAY())")[1]
    )
    assert "UQ_APP_USER_USERNAME_CI" in plan
    assert "IX_TWEET_USER_CREATED" in plan
