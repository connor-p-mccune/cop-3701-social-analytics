-- ============================================================================
-- Alternative loader for Oracle SQLcl users.
--
-- The recommended path is `python -m social_analytics load`, which works
-- with only Python installed. This script uses SQLcl's LOAD command (not
-- available in SQL*Plus or SQL Developer). Run it from the repository root
-- against an empty schema created by sql/01_schema.sql:
--
--     sql analytics/analytics_pw@localhost:1521/FREEPDB1 @sql/load_sqlcl.sql
--
-- Tables are loaded parents-first so foreign keys are satisfied.
-- ============================================================================

LOAD APP_USER data/app_user.csv
LOAD HASHTAG data/hashtag.csv
LOAD TWEET data/tweet.csv
LOAD SENTIMENT_SCORE data/sentiment_score.csv
LOAD TWEET_HASHTAG data/tweet_hashtag.csv
COMMIT;
