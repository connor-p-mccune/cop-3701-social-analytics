import csv
import os
import re
import zipfile
from datetime import datetime

ZIP_PATH = "archive.zip"
DATA_DIR = "data"

TARGET_USERS = 120
TARGET_TWEETS = 300
TARGET_HASHTAGS = 120

os.makedirs(DATA_DIR, exist_ok=True)

hashtag_pattern = re.compile(r"#(\w+)")
space_pattern = re.compile(r"\s+")

def clean_tweet_text(text):
    text = hashtag_pattern.sub("", text)
    text = space_pattern.sub(" ", text).strip()
    return text

def parse_date(date_str):
    parts = date_str.split()
    cleaned = " ".join(parts[:4] + parts[5:])
    dt = datetime.strptime(cleaned, "%a %b %d %H:%M:%S %Y")
    return dt.strftime("%Y-%m-%d %H:%M:%S")

user_map = {}
users = []

hashtag_map = {}
hashtags = []

tweets = []
sentiment_scores = []
tweet_hashtag_rows = []
tweet_hashtag_pairs = set()

next_user_id = 1
next_hashtag_id = 1

with zipfile.ZipFile(ZIP_PATH, "r") as zf:
    csv_name = zf.namelist()[0]

    with zf.open(csv_name) as raw_file:
        import io
        text_file = io.TextIOWrapper(raw_file, encoding="latin-1")
        reader = csv.reader(text_file)

        for row in reader:
            if len(row) != 6:
                continue

            sentiment_raw, tweet_id_raw, date_raw, query_raw, username_raw, tweet_text_raw = row

            try:
                tweet_id = int(tweet_id_raw)
            except ValueError:
                continue

            username = username_raw.strip()
            if not username:
                continue

            cleaned_text = clean_tweet_text(tweet_text_raw)
            if not cleaned_text:
                continue

            hashtags_in_tweet = hashtag_pattern.findall(tweet_text_raw)
            hashtags_in_tweet = [tag.lower() for tag in hashtags_in_tweet if tag.strip()]

            if username not in user_map:
                created_at = parse_date(date_raw)
                user_map[username] = next_user_id
                users.append([
                    next_user_id,
                    username,
                    f"{username.lower()}@example.com",
                    username,
                    "",
                    created_at
                ])
                next_user_id += 1

            user_id = user_map[username]
            created_at = parse_date(date_raw)

            tweets.append([
                tweet_id,
                user_id,
                cleaned_text,
                created_at,
                "en",
                ""
            ])

            if sentiment_raw == "0":
                score = -1.00
            elif sentiment_raw == "4":
                score = 1.00
            else:
                score = 0.00

            sentiment_scores.append([
                tweet_id,
                score,
                "sentiment140",
                created_at
            ])

            for tag in hashtags_in_tweet:
                if tag not in hashtag_map:
                    hashtag_map[tag] = next_hashtag_id
                    hashtags.append([
                        next_hashtag_id,
                        tag,
                        created_at
                    ])
                    next_hashtag_id += 1

                hashtag_id = hashtag_map[tag]
                pair = (tweet_id, hashtag_id)

                if pair not in tweet_hashtag_pairs:
                    tweet_hashtag_pairs.add(pair)
                    tweet_hashtag_rows.append([
                        tweet_id,
                        hashtag_id,
                        created_at
                    ])

            if (
                len(users) >= TARGET_USERS and
                len(tweets) >= TARGET_TWEETS and
                len(hashtags) >= TARGET_HASHTAGS
            ):
                break

with open(os.path.join(DATA_DIR, "app_user.csv"), "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["user_id", "username", "email", "display_name", "location", "created_at"])
    writer.writerows(users)

with open(os.path.join(DATA_DIR, "tweet.csv"), "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["tweet_id", "user_id", "tweet_text", "created_at", "lang", "reply_to_tweet_id"])
    writer.writerows(tweets)

with open(os.path.join(DATA_DIR, "hashtag.csv"), "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["hashtag_id", "tag_text", "first_seen_at"])
    writer.writerows(hashtags)

with open(os.path.join(DATA_DIR, "sentiment_score.csv"), "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["tweet_id", "score", "model_version", "computed_at"])
    writer.writerows(sentiment_scores)

with open(os.path.join(DATA_DIR, "tweet_hashtag.csv"), "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["tweet_id", "hashtag_id", "tagged_at"])
    writer.writerows(tweet_hashtag_rows)

print("Finished generating cleaned CSV files from archive.zip")
print(f"APP_USER rows: {len(users)}")
print(f"TWEET rows: {len(tweets)}")
print(f"HASHTAG rows: {len(hashtags)}")
print(f"SENTIMENT_SCORE rows: {len(sentiment_scores)}")
print(f"TWEET_HASHTAG rows: {len(tweet_hashtag_rows)}")