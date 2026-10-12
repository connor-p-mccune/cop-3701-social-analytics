-- ============================================================================
-- Analytics layer: daily hashtag rollups and the procedure that maintains them.
--
-- Run after 01_schema.sql. Safe to re-run.
-- ============================================================================

BEGIN
   FOR t IN (SELECT table_name FROM user_tables WHERE table_name = 'HASHTAG_DAILY_STATS')
   LOOP
      EXECUTE IMMEDIATE 'DROP TABLE ' || t.table_name || ' CASCADE CONSTRAINTS PURGE';
   END LOOP;
END;
/

-- One row per hashtag per UTC day. This is derived data (controlled
-- redundancy): it can always be rebuilt from TWEET, TWEET_HASHTAG, and
-- SENTIMENT_SCORE, and it exists so that trend queries read a few thousand
-- pre-aggregated rows instead of re-joining every tweet.
--
-- Only additive measures (counts and sums) are stored. Averages and
-- percentages are computed at query time, so they stay correct when days
-- are rolled up into weeks or longer windows.
CREATE TABLE HASHTAG_DAILY_STATS (
    hashtag_id      NUMBER(10)    NOT NULL,
    stat_date       DATE          NOT NULL,
    tweet_count     NUMBER(10)    NOT NULL,
    scored_count    NUMBER(10)    NOT NULL,
    positive_count  NUMBER(10)    NOT NULL,
    negative_count  NUMBER(10)    NOT NULL,
    score_sum       NUMBER(14,4)  NOT NULL,
    refreshed_at    TIMESTAMP     DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT pk_hashtag_daily_stats
        PRIMARY KEY (hashtag_id, stat_date),
    CONSTRAINT fk_hds_hashtag
        FOREIGN KEY (hashtag_id) REFERENCES HASHTAG (hashtag_id) ON DELETE CASCADE,
    CONSTRAINT ck_hds_counts
        CHECK (scored_count <= tweet_count
               AND positive_count + negative_count <= scored_count),
    CONSTRAINT ck_hds_whole_day
        CHECK (stat_date = TRUNC(stat_date))
);

-- Date-window scans across all hashtags (daily leaderboards, weekly trends).
CREATE INDEX ix_hds_stat_date ON HASHTAG_DAILY_STATS (stat_date, hashtag_id);

COMMENT ON TABLE HASHTAG_DAILY_STATS IS
    'Derived daily rollup per hashtag. Maintained by REFRESH_HASHTAG_STATS.';
COMMENT ON COLUMN HASHTAG_DAILY_STATS.stat_date IS 'UTC calendar day (midnight).';
COMMENT ON COLUMN HASHTAG_DAILY_STATS.scored_count IS 'Tweets that have a sentiment score.';
COMMENT ON COLUMN HASHTAG_DAILY_STATS.score_sum IS
    'Sum of sentiment scores; average = score_sum / scored_count.';

-- Recompute HASHTAG_DAILY_STATS for the days in [p_from, p_to] (inclusive,
-- truncated to whole days). Either bound may be NULL to leave that side open,
-- so a call with no arguments rebuilds everything.
--
-- The refresh is idempotent. Rows are inserted, updated only when a value
-- changed, or deleted when a day no longer has any tweets, so re-running it
-- leaves the table unchanged. It does not commit; the caller owns the
-- transaction.
CREATE OR REPLACE PROCEDURE refresh_hashtag_stats (
    p_from IN DATE DEFAULT NULL,
    p_to   IN DATE DEFAULT NULL
) AS
    v_from DATE := TRUNC(p_from);
    v_to   DATE := TRUNC(p_to);
BEGIN
    MERGE INTO HASHTAG_DAILY_STATS s
    USING (
        SELECT th.hashtag_id,
               TRUNC(t.created_at)                     AS stat_date,
               COUNT(*)                                AS tweet_count,
               COUNT(ss.score)                         AS scored_count,
               COUNT(CASE WHEN ss.score > 0 THEN 1 END) AS positive_count,
               COUNT(CASE WHEN ss.score < 0 THEN 1 END) AS negative_count,
               NVL(SUM(ss.score), 0)                   AS score_sum
          FROM TWEET_HASHTAG th
          JOIN TWEET t
            ON t.tweet_id = th.tweet_id
          LEFT JOIN SENTIMENT_SCORE ss
            ON ss.tweet_id = t.tweet_id
         WHERE (v_from IS NULL OR t.created_at >= v_from)
           AND (v_to   IS NULL OR t.created_at <  v_to + 1)
         GROUP BY th.hashtag_id, TRUNC(t.created_at)
    ) src
    ON (s.hashtag_id = src.hashtag_id AND s.stat_date = src.stat_date)
    WHEN MATCHED THEN UPDATE SET
        s.tweet_count    = src.tweet_count,
        s.scored_count   = src.scored_count,
        s.positive_count = src.positive_count,
        s.negative_count = src.negative_count,
        s.score_sum      = src.score_sum,
        s.refreshed_at   = SYSTIMESTAMP
      WHERE s.tweet_count    <> src.tweet_count
         OR s.scored_count   <> src.scored_count
         OR s.positive_count <> src.positive_count
         OR s.negative_count <> src.negative_count
         OR s.score_sum      <> src.score_sum
    WHEN NOT MATCHED THEN INSERT
        (hashtag_id, stat_date, tweet_count, scored_count,
         positive_count, negative_count, score_sum)
    VALUES
        (src.hashtag_id, src.stat_date, src.tweet_count, src.scored_count,
         src.positive_count, src.negative_count, src.score_sum);

    -- Drop rollups for days in the window that no longer have tweets.
    DELETE FROM HASHTAG_DAILY_STATS s
     WHERE (v_from IS NULL OR s.stat_date >= v_from)
       AND (v_to   IS NULL OR s.stat_date <= v_to)
       AND NOT EXISTS (
               SELECT 1
                 FROM TWEET_HASHTAG th
                 JOIN TWEET t
                   ON t.tweet_id = th.tweet_id
                WHERE th.hashtag_id = s.hashtag_id
                  AND t.created_at >= s.stat_date
                  AND t.created_at <  s.stat_date + 1);
END refresh_hashtag_stats;
/
