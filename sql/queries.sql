-- ============================================================================
-- Query catalog
--
-- Every query that the CLI, dashboard, and tests run lives in this file, so
-- the SQL shown in the docs is exactly the SQL that executes. Each entry is:
--
--   -- name: <identifier>
--   -- <one or more lines describing the query>
--   <a single SQL statement ending with a semicolon>
--
-- Bind variables use Oracle's :name syntax.
-- ============================================================================

-- name: tweets_by_user
-- Feature 1: all tweets by a selected user, newest first.
SELECT u.username,
       t.tweet_id,
       t.tweet_text,
       t.created_at
FROM APP_USER u
JOIN TWEET t
    ON u.user_id = t.user_id
WHERE u.username = :username
ORDER BY t.created_at DESC;

-- name: hashtags_for_tweet
-- Feature 2: every hashtag used in a selected tweet.
SELECT t.tweet_id,
       t.tweet_text,
       h.tag_text
FROM TWEET t
JOIN TWEET_HASHTAG th
    ON t.tweet_id = th.tweet_id
JOIN HASHTAG h
    ON th.hashtag_id = h.hashtag_id
WHERE t.tweet_id = :tweet_id
ORDER BY h.tag_text;

-- name: tweets_with_hashtag
-- Feature 3: all tweets that use a selected hashtag, newest first.
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
ORDER BY t.created_at DESC;

-- name: sentiment_in_date_range
-- Feature 4: tweets and their sentiment scores within a date range.
SELECT t.tweet_id,
       t.tweet_text,
       s.score,
       s.model_version,
       t.created_at
FROM TWEET t
JOIN SENTIMENT_SCORE s
    ON t.tweet_id = s.tweet_id
WHERE t.created_at BETWEEN :start_date AND :end_date
ORDER BY t.created_at DESC;

-- name: top_hashtags
-- Feature 5: hashtags ranked by how many tweets use them.
SELECT h.tag_text,
       COUNT(*) AS usage_count
FROM HASHTAG h
JOIN TWEET_HASHTAG th
    ON h.hashtag_id = th.hashtag_id
GROUP BY h.tag_text
ORDER BY usage_count DESC, h.tag_text;
