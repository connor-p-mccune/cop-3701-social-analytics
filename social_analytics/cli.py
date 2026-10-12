import os
import oracledb
from dotenv import load_dotenv

load_dotenv()

oracledb.init_oracle_client(
    lib_dir=r"C:\Users\joyhn\Downloads\cop-3701-stock-market-time-series-db-main\cop-3701-social-analytics\cop-3701-social-analytics\instantclient_23_0"
)

DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_DSN = os.getenv("DB_DSN")


def get_connection():
    return oracledb.connect(
        user=DB_USER,
        password=DB_PASSWORD,
        dsn=DB_DSN
    )


def run_query(query, params=None):
    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        if params:
            cur.execute(query, params)
        else:
            cur.execute(query)

        columns = [desc[0] for desc in cur.description]
        rows = cur.fetchall()
        return columns, rows
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def print_results(columns, rows):
    if not rows:
        print("\nNo results found.\n")
        return

    print()
    print(" | ".join(str(col) for col in columns))
    print("-" * 100)
    for row in rows:
        print(" | ".join(str(item) for item in row))
    print()


FEATURE_1_SQL = """
SELECT u.username,
       t.tweet_id,
       t.tweet_text,
       t.created_at
FROM APP_USER u
JOIN TWEET t
    ON u.user_id = t.user_id
WHERE u.username = :username
ORDER BY t.created_at DESC
"""

FEATURE_2_SQL = """
SELECT t.tweet_id,
       t.tweet_text,
       h.tag_text
FROM TWEET t
JOIN TWEET_HASHTAG th
    ON t.tweet_id = th.tweet_id
JOIN HASHTAG h
    ON th.hashtag_id = h.hashtag_id
WHERE t.tweet_id = :tweet_id
ORDER BY h.tag_text
"""

FEATURE_3_SQL = """
SELECT h.tag_text,
       t.tweet_id,
       t.tweet_text,
       t.created_at
FROM HASHTAG h
JOIN TWEET_HASHTAG th
    ON h.hashtag_id = th.hashtag_id
JOIN TWEET t
    ON th.tweet_id = t.tweet_id
WHERE h.tag_text = :tag_text
ORDER BY t.created_at DESC
"""

FEATURE_4_SQL = """
SELECT t.tweet_id,
       t.tweet_text,
       s.score,
       s.model_version,
       t.created_at
FROM TWEET t
JOIN SENTIMENT_SCORE s
    ON t.tweet_id = s.tweet_id
WHERE t.created_at BETWEEN TO_TIMESTAMP(:start_date, 'YYYY-MM-DD HH24:MI:SS')
                       AND TO_TIMESTAMP(:end_date, 'YYYY-MM-DD HH24:MI:SS')
ORDER BY t.created_at DESC
"""

FEATURE_5_SQL = """
SELECT h.tag_text,
       COUNT(*) AS usage_count
FROM HASHTAG h
JOIN TWEET_HASHTAG th
    ON h.hashtag_id = th.hashtag_id
GROUP BY h.tag_text
ORDER BY usage_count DESC, h.tag_text
"""


def menu():
    while True:
        print("\nSocial Analytics Database - Part E")
        print("1. View all tweets by a selected user")
        print("2. View all hashtags used in a selected tweet")
        print("3. Find all tweets containing a selected hashtag")
        print("4. View tweet sentiment scores in a date range")
        print("5. Show the top hashtags by usage count")
        print("0. Exit")

        choice = input("Choose an option: ").strip()

        if choice == "1":
            username = input("Enter username: ").strip()
            columns, rows = run_query(FEATURE_1_SQL, {"username": username})
            print_results(columns, rows)

        elif choice == "2":
            tweet_id = input("Enter tweet ID: ").strip()
            columns, rows = run_query(
                FEATURE_2_SQL, {"tweet_id": int(tweet_id)})
            print_results(columns, rows)

        elif choice == "3":
            tag_text = input("Enter hashtag text: ").strip()
            columns, rows = run_query(FEATURE_3_SQL, {"tag_text": tag_text})
            print_results(columns, rows)

        elif choice == "4":
            start_date = input(
                "Enter start date (YYYY-MM-DD): ").strip() + " 00:00:00"
            end_date = input(
                "Enter end date (YYYY-MM-DD): ").strip() + " 23:59:59"
            columns, rows = run_query(
                FEATURE_4_SQL,
                {
                    "start_date": start_date,
                    "end_date": end_date
                }
            )
            print_results(columns, rows)

        elif choice == "5":
            columns, rows = run_query(FEATURE_5_SQL)
            print_results(columns, rows)

        elif choice == "0":
            print("Exiting program.")
            break

        else:
            print("Invalid choice. Please try again.")


if __name__ == "__main__":
    menu()
