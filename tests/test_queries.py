import os

import pytest

from social_analytics import queries

CATALOG_TEXT = """
-- Preamble comments are ignored.

-- name: first
-- Describes the first query
-- across two lines.
SELECT TO_CHAR(created_at, 'HH24:MI:SS') AS t
  FROM tweet
 WHERE user_id = :user_id AND tag = :tag AND user_id <> :user_id;

-- ---------------------------------------------------------------
-- A section header that belongs to no query
-- ---------------------------------------------------------------

-- name: second
-- Second.
SELECT 1 FROM dual;
"""


def test_parses_names_descriptions_and_sql():
    parsed = queries.parse_queries(CATALOG_TEXT)
    assert list(parsed) == ["first", "second"]
    first = parsed["first"]
    assert first.description == "Describes the first query across two lines."
    assert first.sql.startswith("SELECT TO_CHAR")
    assert not first.sql.endswith(";")
    assert parsed["second"].sql == "SELECT 1 FROM dual"


def test_binds_are_unique_ordered_and_ignore_string_literals():
    first = queries.parse_queries(CATALOG_TEXT)["first"]
    assert first.binds == ("user_id", "tag")  # not MI or SS from 'HH24:MI:SS'


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("-- name: a\nSELECT 1 FROM dual;\n-- name: a\nSELECT 2 FROM dual;", "duplicate"),
        ("-- name: a\nSELECT 1 FROM dual", "semicolon"),
        ("-- name: a\n-- only a description\n;", "no SQL"),
    ],
)
def test_malformed_catalogs_fail_fast(text, message):
    with pytest.raises(ValueError, match=message):
        queries.parse_queries(text)


def test_project_catalog_has_every_feature_query():
    names = set(queries.catalog())
    features = {
        "tweets_by_user",
        "hashtags_for_tweet",
        "tweets_with_hashtag",
        "sentiment_in_date_range",
        "top_hashtags",
        "daily_top_hashtags",
        "hashtag_daily_trend",
        "hashtag_sentiment_extremes",
        "trending_hashtags",
    }
    assert features <= names
    assert all(query.description for query in queries.catalog().values())


def test_get_unknown_query_raises_key_error():
    with pytest.raises(KeyError, match="no query named"):
        queries.get("does_not_exist")


def test_catalog_reloads_when_the_file_changes(tmp_path):
    path = tmp_path / "queries.sql"
    path.write_text("-- name: a\n-- A.\nSELECT 1 FROM dual;\n")
    assert list(queries.catalog(path)) == ["a"]

    path.write_text(
        "-- name: a\n-- A.\nSELECT 1 FROM dual;\n-- name: b\n-- B.\nSELECT 2 FROM dual;\n"
    )
    os.utime(path, ns=(0, path.stat().st_mtime_ns + 1_000_000))
    assert list(queries.catalog(path)) == ["a", "b"]
