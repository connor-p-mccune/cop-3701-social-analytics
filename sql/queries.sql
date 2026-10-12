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

-- ----------------------------------------------------------------------------
-- Trend analytics (read the HASHTAG_DAILY_STATS rollup from 02_analytics.sql)
-- ----------------------------------------------------------------------------

-- name: daily_top_hashtags
-- Feature 6: each day's top :top_n hashtags between two dates (YYYY-MM-DD),
-- the "top hashtags today" leaderboard for every day in the range. ROW_NUMBER
-- with a tag-name tie-break keeps exactly :top_n rows per day.
SELECT stat_date,
       daily_rank,
       tag_text,
       tweet_count
  FROM (SELECT d.stat_date,
               h.tag_text,
               d.tweet_count,
               ROW_NUMBER() OVER (PARTITION BY d.stat_date
                                  ORDER BY d.tweet_count DESC, h.tag_text) AS daily_rank
          FROM HASHTAG_DAILY_STATS d
          JOIN HASHTAG h
            ON h.hashtag_id = d.hashtag_id
         WHERE d.stat_date BETWEEN TO_DATE(:start_date, 'YYYY-MM-DD')
                               AND TO_DATE(:end_date, 'YYYY-MM-DD'))
 WHERE daily_rank <= :top_n
 ORDER BY stat_date, daily_rank;

-- name: hashtag_daily_trend
-- Feature 7: daily usage and sentiment for one hashtag, plus a 7-day rolling
-- sentiment. The window spans 7 calendar days (RANGE, not ROWS) and weights
-- each day by its tweet count.
SELECT d.stat_date,
       d.tweet_count,
       d.positive_count,
       d.negative_count,
       ROUND(d.score_sum / NULLIF(d.scored_count, 0), 4) AS net_sentiment,
       ROUND(
           SUM(d.score_sum) OVER (ORDER BY d.stat_date
                                  RANGE BETWEEN 6 PRECEDING AND CURRENT ROW)
           / NULLIF(SUM(d.scored_count) OVER (ORDER BY d.stat_date
                                              RANGE BETWEEN 6 PRECEDING AND CURRENT ROW), 0),
           4) AS net_sentiment_7d
  FROM HASHTAG_DAILY_STATS d
  JOIN HASHTAG h
    ON h.hashtag_id = d.hashtag_id
 WHERE h.tag_text = LOWER(LTRIM(TRIM(:hashtag), '#'))
 ORDER BY d.stat_date;

-- name: hashtag_sentiment_extremes
-- Feature 8: the :top_n most positive and most negative hashtags between two
-- dates, among hashtags used in at least :min_tweets tweets in that window.
-- Two ROW_NUMBER windows rank the same rows in opposite directions.
WITH window_stats AS (
    SELECT h.tag_text,
           SUM(d.tweet_count)                                                     AS tweet_count,
           ROUND(SUM(d.score_sum) / SUM(d.scored_count), 4)                       AS net_sentiment,
           ROUND(100 * SUM(d.positive_count) / SUM(d.scored_count), 1)            AS pct_positive
      FROM HASHTAG_DAILY_STATS d
      JOIN HASHTAG h
        ON h.hashtag_id = d.hashtag_id
     WHERE d.stat_date BETWEEN TO_DATE(:start_date, 'YYYY-MM-DD')
                           AND TO_DATE(:end_date, 'YYYY-MM-DD')
     GROUP BY h.tag_text
    HAVING SUM(d.tweet_count) >= :min_tweets
       AND SUM(d.scored_count) > 0
), ranked AS (
    SELECT w.*,
           ROW_NUMBER() OVER (ORDER BY net_sentiment DESC, tweet_count DESC, tag_text) AS positive_rank,
           ROW_NUMBER() OVER (ORDER BY net_sentiment ASC,  tweet_count DESC, tag_text) AS negative_rank
      FROM window_stats w
)
SELECT 'positive' AS side, positive_rank AS side_rank,
       tag_text, tweet_count, net_sentiment, pct_positive
  FROM ranked
 WHERE positive_rank <= :top_n
UNION ALL
SELECT 'negative', negative_rank,
       tag_text, tweet_count, net_sentiment, pct_positive
  FROM ranked
 WHERE negative_rank <= :top_n
 ORDER BY side DESC, side_rank;

-- name: trending_hashtags
-- Feature 9: the :top_n hashtags whose usage grew most in the ISO week
-- (Monday-Sunday) containing :week_of, compared with the week before. LAG()
-- finds each hashtag's previous active week; if that is not the immediately
-- preceding week, the hashtag had zero uses last week.
WITH weekly AS (
    SELECT d.hashtag_id,
           TRUNC(d.stat_date, 'IW') AS week_start,
           SUM(d.tweet_count)       AS uses
      FROM HASHTAG_DAILY_STATS d
     WHERE d.stat_date >= TRUNC(TO_DATE(:week_of, 'YYYY-MM-DD'), 'IW') - 7
       AND d.stat_date <  TRUNC(TO_DATE(:week_of, 'YYYY-MM-DD'), 'IW') + 7
     GROUP BY d.hashtag_id, TRUNC(d.stat_date, 'IW')
), with_previous AS (
    SELECT w.*,
           LAG(w.week_start) OVER (PARTITION BY w.hashtag_id ORDER BY w.week_start) AS prev_week,
           LAG(w.uses)       OVER (PARTITION BY w.hashtag_id ORDER BY w.week_start) AS prev_uses
      FROM weekly w
), compared AS (
    SELECT p.hashtag_id,
           p.week_start,
           p.uses,
           CASE WHEN p.prev_week = p.week_start - 7 THEN p.prev_uses ELSE 0 END AS prev_week_uses
      FROM with_previous p
     WHERE p.week_start = TRUNC(TO_DATE(:week_of, 'YYYY-MM-DD'), 'IW')
)
SELECT h.tag_text,
       c.week_start,
       c.uses,
       c.prev_week_uses,
       c.uses - c.prev_week_uses AS change,
       CASE WHEN c.prev_week_uses > 0
            THEN ROUND(100 * (c.uses - c.prev_week_uses) / c.prev_week_uses)
       END AS growth_pct
  FROM compared c
  JOIN HASHTAG h
    ON h.hashtag_id = c.hashtag_id
 ORDER BY change DESC, c.uses DESC, h.tag_text
 FETCH FIRST :top_n ROWS ONLY;

-- ----------------------------------------------------------------------------
-- Summary queries used by the CLI header and dashboard
-- ----------------------------------------------------------------------------

-- name: dataset_overview
-- Headline counts, share of positive tweets, and the date span of the data.
SELECT (SELECT COUNT(*) FROM TWEET)         AS tweets,
       (SELECT COUNT(*) FROM APP_USER)      AS users,
       (SELECT COUNT(*) FROM HASHTAG)       AS hashtags,
       (SELECT COUNT(*) FROM TWEET_HASHTAG) AS hashtag_links,
       (SELECT ROUND(100 * AVG(CASE WHEN score > 0 THEN 1 ELSE 0 END), 1)
          FROM SENTIMENT_SCORE)             AS pct_positive,
       (SELECT TRUNC(MIN(created_at)) FROM TWEET) AS first_day,
       (SELECT TRUNC(MAX(created_at)) FROM TWEET) AS last_day
  FROM DUAL;

-- name: period_summary
-- Headline figures for a date range: tweets, distinct authors, hashtags in
-- use, and the share of scored tweets that are positive.
SELECT a.tweets,
       a.users,
       (SELECT COUNT(DISTINCT d.hashtag_id)
          FROM HASHTAG_DAILY_STATS d
         WHERE d.stat_date BETWEEN TO_DATE(:start_date, 'YYYY-MM-DD')
                               AND TO_DATE(:end_date, 'YYYY-MM-DD')) AS hashtags,
       a.pct_positive
  FROM (SELECT COUNT(*)                  AS tweets,
               COUNT(DISTINCT t.user_id) AS users,
               ROUND(100 * AVG(CASE WHEN s.score > 0 THEN 1
                                    WHEN s.score IS NOT NULL THEN 0 END), 1) AS pct_positive
          FROM TWEET t
          LEFT JOIN SENTIMENT_SCORE s
            ON s.tweet_id = t.tweet_id
         WHERE t.created_at >= TO_DATE(:start_date, 'YYYY-MM-DD')
           AND t.created_at <  TO_DATE(:end_date, 'YYYY-MM-DD') + 1) a;

-- name: daily_activity
-- Daily volume and sentiment between two dates. The view computes the 7-day
-- rolling value before this filter applies, so the first days of the range
-- still average in the days just before it.
SELECT activity_date,
       tweet_count,
       positive_count,
       negative_count,
       net_sentiment,
       net_sentiment_7d
  FROM v_daily_activity
 WHERE activity_date BETWEEN TO_DATE(:start_date, 'YYYY-MM-DD')
                         AND TO_DATE(:end_date, 'YYYY-MM-DD')
 ORDER BY activity_date;

-- name: top_hashtags_in_range
-- The :row_limit most-used hashtags between two dates, with net sentiment.
SELECT h.tag_text,
       SUM(d.tweet_count)                                          AS tweet_count,
       ROUND(SUM(d.score_sum) / NULLIF(SUM(d.scored_count), 0), 4) AS net_sentiment
  FROM HASHTAG_DAILY_STATS d
  JOIN HASHTAG h
    ON h.hashtag_id = d.hashtag_id
 WHERE d.stat_date BETWEEN TO_DATE(:start_date, 'YYYY-MM-DD')
                       AND TO_DATE(:end_date, 'YYYY-MM-DD')
 GROUP BY h.tag_text
 ORDER BY tweet_count DESC, h.tag_text
 FETCH FIRST :row_limit ROWS ONLY;

-- name: popular_hashtags
-- Lifetime stats for hashtags used in at least :min_tweets tweets, most used
-- first.
SELECT tag_text,
       tweet_count,
       net_sentiment,
       pct_positive,
       active_days,
       first_day,
       last_day
  FROM v_hashtag_sentiment
 WHERE tweet_count >= :min_tweets
 ORDER BY tweet_count DESC, tag_text;

-- name: hashtag_period_summary
-- One hashtag's usage and sentiment between two dates (always one row; the
-- measures are NULL when the hashtag was not used in the range).
SELECT NVL(SUM(d.tweet_count), 0)                                              AS tweet_count,
       ROUND(SUM(d.score_sum) / NULLIF(SUM(d.scored_count), 0), 4)            AS net_sentiment,
       ROUND(100 * SUM(d.positive_count) / NULLIF(SUM(d.scored_count), 0), 1) AS pct_positive,
       COUNT(*)                                                               AS active_days
  FROM HASHTAG_DAILY_STATS d
  JOIN HASHTAG h
    ON h.hashtag_id = d.hashtag_id
 WHERE h.tag_text = LOWER(LTRIM(TRIM(:hashtag), '#'))
   AND d.stat_date BETWEEN TO_DATE(:start_date, 'YYYY-MM-DD')
                       AND TO_DATE(:end_date, 'YYYY-MM-DD');
