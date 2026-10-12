import csv
import io
import zipfile
from collections import Counter
from datetime import datetime

import pytest

from social_analytics.etl import preprocess as pp

REPLACEMENT_CHAR = chr(0xFFFD)


def source_row(label, tweet_id, when, user, text):
    """A row in Sentiment140's six-column layout."""
    return [label, str(tweet_id), when, "NO_QUERY", user, text]


# --------------------------------------------------------------------------
# Parsing and cleaning
# --------------------------------------------------------------------------


class TestParseTimestamp:
    def test_converts_pdt_to_utc(self):
        assert pp.parse_timestamp("Mon Apr 06 22:19:45 PDT 2009") == datetime(2009, 4, 7, 5, 19, 45)

    def test_converts_pst_to_utc(self):
        assert pp.parse_timestamp("Sun Jan 04 23:00:00 PST 2009") == datetime(2009, 1, 5, 7, 0, 0)

    def test_rejects_unknown_zone(self):
        with pytest.raises(ValueError, match="unknown time zone"):
            pp.parse_timestamp("Mon Apr 06 22:19:45 EST 2009")


class TestCleanText:
    def test_decodes_html_entities(self):
        assert pp.clean_text("Tom &amp; Jerry &lt;3 &quot;hi&quot;") == 'Tom & Jerry <3 "hi"'

    def test_restores_lost_apostrophes(self):
        assert pp.clean_text(f"I{REPLACEMENT_CHAR}m here") == "I'm here"

    def test_collapses_whitespace(self):
        assert pp.clean_text("  so \t much\n space  ") == "so much space"


class TestExtractHashtags:
    def test_lowercases_and_deduplicates_in_order(self):
        assert pp.extract_hashtags("#FollowFriday #E3 #followfriday") == ("followfriday", "e3")

    def test_drops_purely_numeric_tags(self):
        assert pp.extract_hashtags("#1 fan of #24 and #f1") == ("f1",)

    def test_ignores_html_entities_and_url_fragments(self):
        text = pp.clean_text("it&#39;s at http://example.com/#anchor #real")
        assert pp.extract_hashtags(text) == ("real",)

    def test_requires_a_word_boundary_before_the_hash(self):
        assert pp.extract_hashtags("C#sharp vs #python") == ("python",)


def test_decode_line_falls_back_to_cp1252():
    assert pp.decode_line("café".encode()) == "café"
    assert pp.decode_line("We\xb4ll".encode("cp1252")) == "We´ll"


def test_is_garbled_flags_mostly_non_ascii_text():
    assert pp.is_garbled("ë‹¬ë?œ ê°œë°œìž?")
    assert not pp.is_garbled("We´ll give u a special #Dravensday")


class TestParseRow:
    def test_builds_tweet(self):
        tweet = pp.parse_row(
            source_row("4", 42, "Mon Apr 06 22:19:45 PDT 2009", " Alice ", "Hi #There")
        )
        assert tweet == pp.Tweet(
            tweet_id=42,
            username="Alice",
            created_at=datetime(2009, 4, 7, 5, 19, 45),
            text="Hi #There",
            score=1.0,
            hashtags=("there",),
        )

    @pytest.mark.parametrize(
        "row",
        [
            source_row("9", 1, "Mon Apr 06 22:19:45 PDT 2009", "a", "bad label"),
            source_row("0", "x1", "Mon Apr 06 22:19:45 PDT 2009", "a", "bad id"),
            source_row("0", 1, "Mon Apr 06 22:19:45 PDT 2009", " ", "no user"),
            source_row("0", 1, "Mon Apr 06 22:19:45 PDT 2009", "a", "   "),
            source_row("0", 1, "Mon Apr 06 22:19:45 PDT 2009", "a", "ë‹¬ë?œ ê°œë°œìž?"),
            ["0", "1", "too", "short"],
        ],
    )
    def test_rejects_unusable_rows(self, row):
        assert pp.parse_row(row) is None


# --------------------------------------------------------------------------
# Sampling
# --------------------------------------------------------------------------


def test_stable_fraction_is_deterministic_and_seeded():
    values = [pp.stable_fraction(42, key) for key in range(1000)]
    assert values == [pp.stable_fraction(42, key) for key in range(1000)]
    assert all(0 <= v < 1 for v in values)
    assert values != [pp.stable_fraction(7, key) for key in range(1000)]
    assert 0.45 < sum(values) / len(values) < 0.55


def test_select_timeline_users_respects_bounds_and_count():
    counts = Counter({"few": 2, "a": 8, "b": 20, "c": 40, "many": 500})
    picked = pp.select_timeline_users(counts, count=2, min_tweets=8, max_tweets=40, seed=1)
    assert len(picked) == 2
    assert picked <= {"a", "b", "c"}
    assert picked == pp.select_timeline_users(counts, 2, 8, 40, seed=1)


def test_scan_corpus_finds_duplicates_and_label_window():
    rows = [
        source_row("0", 1, "Mon Apr 06 10:00:00 PDT 2009", "Ann", "neg early"),
        source_row("0", 2, "Thu Jun 25 10:00:00 PDT 2009", "ann", "neg late"),
        source_row("4", 3, "Mon Apr 06 12:00:00 PDT 2009", "bob", "pos early"),
        source_row("4", 4, "Tue Jun 16 08:00:00 PDT 2009", "bob", "pos late"),
        source_row("4", 1, "Wed May 06 10:00:00 PDT 2009", "ann", "relabeled duplicate"),
    ]
    scan = pp.scan_corpus(rows)
    assert scan.duplicate_ids == {1}
    assert scan.tweet_counts == Counter({"ann": 3, "bob": 2})
    # The window runs from the latest label start to the earliest label end.
    assert scan.window == (datetime(2009, 4, 6, 19, 0), datetime(2009, 6, 16, 15, 0))


def test_sample_tweets_applies_window_exclusions_and_timelines():
    window = (datetime(2009, 4, 7), datetime(2009, 6, 1))
    rows = [
        source_row("0", 1, "Wed Apr 08 10:00:00 PDT 2009", "ann", "kept #tag"),
        source_row("0", 2, "Wed Apr 08 10:00:00 PDT 2009", "ann", "excluded duplicate"),
        source_row("0", 3, "Thu Jun 25 10:00:00 PDT 2009", "ann", "outside window #tag"),
        source_row("4", 4, "Wed Apr 08 11:00:00 PDT 2009", "Tim", "timeline user"),
        source_row("4", 5, "Wed Apr 08 12:00:00 PDT 2009", "zed", "plain, rate 0"),
    ]
    sample = pp.sample_tweets(
        rows,
        seed=42,
        hashtag_rate=1.0,
        plain_rate=0.0,
        timeline_users={"tim"},
        excluded_ids={2},
        window=window,
    )
    assert [t.tweet_id for t in sample] == [1, 4]


# --------------------------------------------------------------------------
# Normalization and output
# --------------------------------------------------------------------------


def tweet(tweet_id, user, when, tags=(), score=1.0):
    return pp.Tweet(tweet_id, user, when, f"text {tweet_id}", score, tuple(tags))


def test_build_tables_assigns_ids_by_first_appearance():
    tables = pp.build_tables(
        [
            tweet(30, "Bob", datetime(2009, 5, 3), ["b"], score=-1.0),
            tweet(10, "ann", datetime(2009, 5, 1), ["a", "b"]),
            tweet(20, "ANN", datetime(2009, 5, 2), ["a"]),
        ]
    )
    # Users match case-insensitively; the earliest spelling and time win.
    assert tables.app_user == [
        [1, "ann", "ann@example.com", "ann", "", "2009-05-01 00:00:00"],
        [2, "Bob", "bob@example.com", "Bob", "", "2009-05-03 00:00:00"],
    ]
    assert tables.hashtag == [[1, "a", "2009-05-01 00:00:00"], [2, "b", "2009-05-01 00:00:00"]]
    assert [row[:2] for row in tables.tweet] == [[10, 1], [20, 1], [30, 2]]
    scores = [row[:2] for row in tables.sentiment_score]
    assert scores == [[10, "1.00"], [20, "1.00"], [30, "-1.00"]]
    assert [row[:2] for row in tables.tweet_hashtag] == [[10, 1], [10, 2], [20, 1], [30, 2]]


def write_fixture_zip(path):
    """A miniature Sentiment140 archive whose test file is listed first."""
    rows = [
        source_row("0", 1, "Mon Apr 06 22:00:00 PDT 2009", "ann", "sad #Monday &amp; tired"),
        source_row("4", 2, "Mon Apr 06 22:00:00 PDT 2009", "bob", "happy #monday"),
        source_row("4", 3, "Tue Apr 07 09:00:00 PDT 2009", "Ann", "better now"),
        source_row("0", 4, "Tue Apr 07 09:00:00 PDT 2009", "cat", "meh"),
    ]
    buffer = io.StringIO()
    csv.writer(buffer, quoting=csv.QUOTE_ALL).writerows(rows)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("testdata.manual.2009.06.14.csv", '"2","9","x","q","u","ignored"\n')
        archive.writestr("training.1600000.processed.noemoticon.csv", buffer.getvalue())


def test_main_writes_identical_csvs_on_every_run(tmp_path):
    archive = tmp_path / "sentiment140.zip"
    write_fixture_zip(archive)
    args = ["--input", str(archive), "--hashtag-rate", "1", "--plain-rate", "1"]

    pp.main([*args, "--output", str(tmp_path / "run1")])
    pp.main([*args, "--output", str(tmp_path / "run2")])

    for name, header in pp.CSV_HEADERS.items():
        first = (tmp_path / "run1" / f"{name}.csv").read_text(encoding="utf-8")
        assert first == (tmp_path / "run2" / f"{name}.csv").read_text(encoding="utf-8")
        assert first.splitlines()[0] == ",".join(header)

    tweets = (tmp_path / "run1" / "tweet.csv").read_text(encoding="utf-8")
    assert "sad #Monday & tired" in tweets
    assert "ignored" not in tweets  # the test-set member was skipped
    users = (tmp_path / "run1" / "app_user.csv").read_text(encoding="utf-8").splitlines()
    assert len(users) == 1 + 3  # ann/Ann merged


def test_iter_source_rows_requires_a_training_member(tmp_path):
    archive = tmp_path / "other.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("notes.txt", "nothing here")
    with pytest.raises(ValueError, match="training"):
        list(pp.iter_source_rows(archive))
