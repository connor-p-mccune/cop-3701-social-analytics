"""Build the sample dataset in data/ from the Sentiment140 corpus.

Sentiment140 (Go, Bhayani & Huang, 2009) holds 1.6M English tweets from
April-June 2009, each labeled negative (0) or positive (4). Three
properties of the source shape this script:

* The CSV is sorted by label: the first 800,000 rows are all negative. A
  "first N rows" sample is therefore 100% negative and spans only a few
  days, so this script samples across the entire file instead.
* 1,685 tweet ids appear twice with opposite labels. Those tweets have no
  trustworthy label and are dropped.
* The two labels were collected over different periods: positive tweets
  stop at 15:40 UTC on June 16, while negative tweets continue to June 25.
  After that point, sentiment would look 100% negative purely because of
  how the corpus was collected, so the sample is limited to the period in
  which both labels were being collected.

Sampling is deterministic: every keep/drop decision is a hash of --seed and
the tweet id (or username), so reruns produce byte-identical CSVs. The
sample combines three slices:

1. Tweets with hashtags, kept at --hashtag-rate, so per-hashtag trends have
   real volume (only ~2% of the corpus uses hashtags).
2. All other tweets, kept at --plain-rate. This preserves the corpus's
   day-by-day volume and label mix.
3. Complete timelines for --timeline-users users with a moderate number of
   tweets, so per-user lookups return real histories.

Usage:
    python -m social_analytics preprocess --input raw/trainingandtestdata.zip
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import re
import zipfile
from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

TRAINING_MEMBER_PREFIX = "training."
TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"
MODEL_VERSION = "sentiment140"

# Sentiment140 timestamps carry a US Pacific zone abbreviation.
ZONE_OFFSETS = {"PDT": timedelta(hours=-7), "PST": timedelta(hours=-8)}
LABEL_SCORES = {"0": -1.0, "2": 0.0, "4": 1.0}

# A hashtag must not be glued to a preceding word, URL path, or HTML entity,
# and (as on Twitter) must contain at least one non-digit character.
HASHTAG_PATTERN = re.compile(r"(?<![\w&/])#(\w+)")
WHITESPACE_PATTERN = re.compile(r"\s+")

# About 1,100 rows hold Korean or Cyrillic text that was double-encoded
# before the corpus was published ("ë‹¬ë?œ"); bytes were lost, so it cannot
# be repaired. The corpus is meant to be English, so such rows are dropped.
MAX_NON_ASCII_SHARE = 0.2


@dataclass(frozen=True)
class Tweet:
    tweet_id: int
    username: str
    created_at: datetime
    text: str
    score: float
    hashtags: tuple[str, ...]


@dataclass(frozen=True)
class CorpusScan:
    """Facts about the whole corpus gathered by the first pass."""

    tweet_counts: Counter[str]  # tweets per lowercase username
    duplicate_ids: set[int]
    window: tuple[datetime, datetime]  # period during which every label was collected


@dataclass
class Tables:
    """Rows for each CSV in data/, in load order."""

    app_user: list[list]
    hashtag: list[list]
    tweet: list[list]
    sentiment_score: list[list]
    tweet_hashtag: list[list]


CSV_HEADERS = {
    "app_user": ["user_id", "username", "email", "display_name", "location", "created_at"],
    "hashtag": ["hashtag_id", "tag_text", "first_seen_at"],
    "tweet": ["tweet_id", "user_id", "tweet_text", "created_at", "lang", "reply_to_tweet_id"],
    "sentiment_score": ["tweet_id", "score", "model_version", "computed_at"],
    "tweet_hashtag": ["tweet_id", "hashtag_id", "tagged_at"],
}


# --------------------------------------------------------------------------
# Parsing and cleaning
# --------------------------------------------------------------------------


def decode_line(raw: bytes) -> str:
    """Decode one source line; the corpus mixes UTF-8 and cp1252 rows."""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


def iter_source_rows(path: Path) -> Iterator[list[str]]:
    """Yield CSV rows from the Sentiment140 zip (Stanford or Kaggle) or CSV."""
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as archive:
            member = next(
                (n for n in archive.namelist() if Path(n).name.startswith(TRAINING_MEMBER_PREFIX)),
                None,
            )
            if member is None:
                raise ValueError(f"{path} has no {TRAINING_MEMBER_PREFIX}* CSV member")
            with archive.open(member) as raw:
                yield from csv.reader(decode_line(line) for line in raw)
    else:
        with path.open("rb") as raw:
            yield from csv.reader(decode_line(line) for line in raw)


def parse_timestamp(value: str) -> datetime:
    """Convert 'Mon Apr 06 22:19:45 PDT 2009' to a naive UTC datetime."""
    _weekday, month, day, clock, zone, year = value.split()
    if zone not in ZONE_OFFSETS:
        raise ValueError(f"unknown time zone {zone!r} in {value!r}")
    local = datetime.strptime(f"{month} {day} {year} {clock}", "%b %d %Y %H:%M:%S")
    return local - ZONE_OFFSETS[zone]


def clean_text(value: str) -> str:
    """Decode HTML entities and normalize whitespace.

    The replacement character U+FFFD marks characters the source had already
    lost. Nearly all were curly apostrophes ("I'm"), so they are restored as
    plain apostrophes.
    """
    text = html.unescape(value).replace("\ufffd", "'")
    return WHITESPACE_PATTERN.sub(" ", text).strip()


def is_garbled(text: str) -> bool:
    """True for text that is mostly non-ASCII, i.e. corrupted non-English rows."""
    return sum(ord(ch) > 127 for ch in text) > MAX_NON_ASCII_SHARE * len(text)


def extract_hashtags(text: str) -> tuple[str, ...]:
    """Return unique lowercase hashtags in order of appearance."""
    tags: dict[str, None] = {}
    for match in HASHTAG_PATTERN.findall(text):
        tag = match.lower()
        if not tag.isdigit():
            tags.setdefault(tag, None)
    return tuple(tags)


def parse_row(row: list[str]) -> Tweet | None:
    """Turn a raw CSV row into a Tweet, or None if the row is unusable."""
    if len(row) != 6:
        return None
    label, tweet_id, timestamp, _query, username, raw_text = row
    username = username.strip()
    text = clean_text(raw_text)
    if label not in LABEL_SCORES or not tweet_id.isdigit() or not username or not text:
        return None
    if is_garbled(text):
        return None
    return Tweet(
        tweet_id=int(tweet_id),
        username=username,
        created_at=parse_timestamp(timestamp),
        text=text,
        score=LABEL_SCORES[label],
        hashtags=extract_hashtags(text),
    )


# --------------------------------------------------------------------------
# Sampling
# --------------------------------------------------------------------------


def stable_fraction(seed: int, key: object) -> float:
    """Map (seed, key) to a reproducible pseudo-random number in [0, 1)."""
    digest = hashlib.blake2b(f"{seed}:{key}".encode(), digest_size=8).digest()
    return int.from_bytes(digest, "big") / 2**64


def select_timeline_users(
    tweet_counts: Counter[str], count: int, min_tweets: int, max_tweets: int, seed: int
) -> set[str]:
    """Pick `count` users whose tweet totals fall within [min_tweets, max_tweets]."""
    eligible = [user for user, n in tweet_counts.items() if min_tweets <= n <= max_tweets]
    eligible.sort(key=lambda user: (stable_fraction(seed, f"user:{user}"), user))
    return set(eligible[:count])


def scan_corpus(rows: Iterable[list[str]]) -> CorpusScan:
    """First pass: per-user counts, duplicate ids, and the label-coverage window."""
    tweet_counts: Counter[str] = Counter()
    seen: set[int] = set()
    duplicates: set[int] = set()
    label_spans: dict[str, tuple[datetime, datetime]] = {}
    for row in rows:
        # Text is not needed here, so skip the comparatively expensive full parse.
        if len(row) != 6 or row[0] not in LABEL_SCORES or not row[1].isdigit():
            continue
        tweet_id = int(row[1])
        tweet_counts[row[4].strip().lower()] += 1
        if tweet_id in seen:
            duplicates.add(tweet_id)
        seen.add(tweet_id)

        created_at = parse_timestamp(row[2])
        first, last = label_spans.get(row[0], (created_at, created_at))
        label_spans[row[0]] = (min(first, created_at), max(last, created_at))

    if not label_spans:
        raise ValueError("no usable rows in input")
    window = (
        max(first for first, _ in label_spans.values()),
        min(last for _, last in label_spans.values()),
    )
    return CorpusScan(tweet_counts, duplicates, window)


def sample_tweets(
    rows: Iterable[list[str]],
    *,
    seed: int,
    hashtag_rate: float,
    plain_rate: float,
    timeline_users: set[str],
    excluded_ids: set[int],
    window: tuple[datetime, datetime],
) -> list[Tweet]:
    """Second pass: keep in-window tweets selected by any of the sampling slices."""
    sample: dict[int, Tweet] = {}
    for row in rows:
        tweet = parse_row(row)
        if tweet is None or tweet.tweet_id in excluded_ids:
            continue
        if not window[0] <= tweet.created_at <= window[1]:
            continue
        rate = hashtag_rate if tweet.hashtags else plain_rate
        if tweet.username.lower() in timeline_users or stable_fraction(seed, tweet.tweet_id) < rate:
            sample[tweet.tweet_id] = tweet
    return sorted(sample.values(), key=lambda t: (t.created_at, t.tweet_id))


# --------------------------------------------------------------------------
# Normalization into relational tables
# --------------------------------------------------------------------------


def fmt(ts: datetime) -> str:
    return ts.strftime(TIMESTAMP_FORMAT)


def build_tables(tweets: list[Tweet]) -> Tables:
    """Normalize sampled tweets into the five tables of the schema.

    Surrogate keys are assigned in order of first appearance so that ids
    are stable across runs. Usernames are matched case-insensitively, as
    on Twitter. The source has no account creation date, so a user's
    created_at is the time of their earliest tweet in the corpus sample.
    """
    tweets = sorted(tweets, key=lambda t: (t.created_at, t.tweet_id))

    user_ids: dict[str, int] = {}
    app_user: list[list] = []
    hashtag_ids: dict[str, int] = {}
    hashtag: list[list] = []
    tweet_rows: list[list] = []
    sentiment_score: list[list] = []
    tweet_hashtag: list[list] = []

    for t in tweets:
        user_key = t.username.lower()
        if user_key not in user_ids:
            user_ids[user_key] = len(user_ids) + 1
            app_user.append(
                [
                    user_ids[user_key],
                    t.username,
                    f"{user_key}@example.com",
                    t.username,
                    "",
                    fmt(t.created_at),
                ]
            )
        for tag in t.hashtags:
            if tag not in hashtag_ids:
                hashtag_ids[tag] = len(hashtag_ids) + 1
                hashtag.append([hashtag_ids[tag], tag, fmt(t.created_at)])
            tweet_hashtag.append([t.tweet_id, hashtag_ids[tag], fmt(t.created_at)])

        tweet_rows.append([t.tweet_id, user_ids[user_key], t.text, fmt(t.created_at), "en", ""])
        sentiment_score.append([t.tweet_id, f"{t.score:.2f}", MODEL_VERSION, fmt(t.created_at)])

    tweet_rows.sort(key=lambda r: r[0])
    sentiment_score.sort(key=lambda r: r[0])
    tweet_hashtag.sort(key=lambda r: (r[0], r[1]))
    return Tables(app_user, hashtag, tweet_rows, sentiment_score, tweet_hashtag)


def write_csvs(tables: Tables, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, header in CSV_HEADERS.items():
        with (output_dir / f"{name}.csv").open("w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh, lineterminator="\n")
            writer.writerow(header)
            writer.writerows(getattr(tables, name))


def summarize(tables: Tables) -> str:
    scores = Counter(row[1] for row in tables.sentiment_score)
    days = sorted({row[3][:10] for row in tables.tweet})
    tag_names = {row[0]: row[1] for row in tables.hashtag}
    top = Counter(tag_names[row[1]] for row in tables.tweet_hashtag).most_common(8)
    lines = [
        *(f"{name:>16}: {len(getattr(tables, name)):>6,} rows" for name in CSV_HEADERS),
        f"{'labels':>16}: {scores['1.00']:,} positive / {scores['-1.00']:,} negative",
        f"{'date span':>16}: {days[0]} .. {days[-1]} ({len(days)} distinct days)",
        f"{'top hashtags':>16}: " + ", ".join(f"#{tag} ({n})" for tag, n in top),
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Command line
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m social_analytics preprocess",
        description="Sample the Sentiment140 corpus into the CSV files under data/.",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("raw/trainingandtestdata.zip"),
        help="Sentiment140 zip (Stanford or Kaggle) or the extracted training CSV",
    )
    parser.add_argument("--output", type=Path, default=Path("data"))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--hashtag-rate", type=float, default=0.25)
    parser.add_argument("--plain-rate", type=float, default=0.002)
    parser.add_argument("--timeline-users", type=int, default=100)
    parser.add_argument("--timeline-min", type=int, default=8)
    parser.add_argument("--timeline-max", type=int, default=40)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)

    print(f"Scanning {args.input} ...")
    scan = scan_corpus(iter_source_rows(args.input))
    timeline_users = select_timeline_users(
        scan.tweet_counts, args.timeline_users, args.timeline_min, args.timeline_max, args.seed
    )
    print(f"Dropping {len(scan.duplicate_ids):,} tweet ids that appear with conflicting labels")
    start, end = (fmt(ts) for ts in scan.window)
    print(f"Keeping tweets from the period every label covers: {start} .. {end} UTC")

    print("Sampling ...")
    tweets = sample_tweets(
        iter_source_rows(args.input),
        seed=args.seed,
        hashtag_rate=args.hashtag_rate,
        plain_rate=args.plain_rate,
        timeline_users=timeline_users,
        excluded_ids=scan.duplicate_ids,
        window=scan.window,
    )
    tables = build_tables(tweets)
    write_csvs(tables, args.output)
    print(f"Wrote {args.output}/\n{summarize(tables)}")


if __name__ == "__main__":
    main()
