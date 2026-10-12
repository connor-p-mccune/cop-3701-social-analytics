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
-- Feature 1: all tweets by a user, newest first. The match ignores case and a
-- leading @, and uses the function-based index on LOWER(username).
SELECT u.username,
       t.tweet_id,
       t.tweet_text,
       t.created_at
  FROM APP_USER u
  JOIN TWEET t
    ON t.user_id = u.user_id
 WHERE LOWER(u.username) = LOWER(LTRIM(TRIM(:username), '@'))
 ORDER BY t.created_at DESC;

-- name: hashtags_for_tweet
-- Feature 2: every hashtag used in a tweet.
SELECT t.tweet_id,
       t.tweet_text,
       h.tag_text
  FROM TWEET t
  JOIN TWEET_HASHTAG th
    ON th.tweet_id = t.tweet_id
  JOIN HASHTAG h
    ON h.hashtag_id = th.hashtag_id
 WHERE t.tweet_id = :tweet_id
 ORDER BY h.tag_text;

-- name: tweets_with_hashtag
-- Feature 3: all tweets that use a hashtag, newest first. Input is normalized
-- the same way the ETL stores tags ("#FollowFriday" matches "followfriday").
SELECT h.tag_text,
       t.tweet_id,
       t.tweet_text,
       s.score,
       t.created_at
  FROM HASHTAG h
  JOIN TWEET_HASHTAG th
    ON th.hashtag_id = h.hashtag_id
  JOIN TWEET t
    ON t.tweet_id = th.tweet_id
  LEFT JOIN SENTIMENT_SCORE s
    ON s.tweet_id = t.tweet_id
 WHERE h.tag_text = LOWER(LTRIM(TRIM(:hashtag), '#'))
 ORDER BY t.created_at DESC;

-- name: sentiment_in_date_range
-- Feature 4: tweets and their sentiment scores between two dates (inclusive,
-- YYYY-MM-DD). The half-open range [start, end + 1 day) includes every moment
-- of the last day, and explicit TO_DATE formats avoid relying on session NLS
-- settings.
SELECT t.tweet_id,
       t.tweet_text,
       s.score,
       s.model_version,
       t.created_at
  FROM TWEET t
  JOIN SENTIMENT_SCORE s
    ON s.tweet_id = t.tweet_id
 WHERE t.created_at >= TO_DATE(:start_date, 'YYYY-MM-DD')
   AND t.created_at <  TO_DATE(:end_date, 'YYYY-MM-DD') + 1
 ORDER BY t.created_at DESC;

-- name: top_hashtags
-- Feature 5: the most-used hashtags, limited to :row_limit rows.
SELECT h.tag_text,
       COUNT(*) AS usage_count
  FROM HASHTAG h
  JOIN TWEET_HASHTAG th
    ON th.hashtag_id = h.hashtag_id
 GROUP BY h.tag_text
 ORDER BY usage_count DESC, h.tag_text
 FETCH FIRST :row_limit ROWS ONLY;
