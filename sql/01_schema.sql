-- ============================================================================
-- Tweet analytics schema (Oracle 12.1+)
--
-- Five tables in BCNF; see docs/database-design.md for the ER diagram and
-- functional-dependency analysis. Safe to re-run: existing tables are
-- dropped first.
-- ============================================================================

BEGIN
   FOR t IN (SELECT table_name
               FROM user_tables
              WHERE table_name IN ('TWEET_HASHTAG', 'SENTIMENT_SCORE', 'TWEET',
                                   'HASHTAG', 'APP_USER'))
   LOOP
      EXECUTE IMMEDIATE 'DROP TABLE ' || t.table_name || ' CASCADE CONSTRAINTS PURGE';
   END LOOP;
END;
/

CREATE TABLE APP_USER (
    user_id       NUMBER(10)          CONSTRAINT pk_app_user PRIMARY KEY,
    username      VARCHAR2(50 CHAR)   NOT NULL,
    email         VARCHAR2(100 CHAR)  NOT NULL CONSTRAINT uq_app_user_email UNIQUE,
    display_name  VARCHAR2(100 CHAR),
    location      VARCHAR2(100 CHAR),
    created_at    TIMESTAMP           NOT NULL
);

-- Twitter handles are unique regardless of case ("Bob" and "bob" are the
-- same account). A function-based unique index enforces that rule and also
-- serves case-insensitive lookups such as WHERE LOWER(username) = :name.
CREATE UNIQUE INDEX uq_app_user_username_ci ON APP_USER (LOWER(username));

CREATE TABLE TWEET (
    tweet_id           NUMBER(19)          CONSTRAINT pk_tweet PRIMARY KEY,
    user_id            NUMBER(10)          NOT NULL,
    tweet_text         VARCHAR2(280 CHAR)  NOT NULL,
    created_at         TIMESTAMP           NOT NULL,
    lang               VARCHAR2(10),
    reply_to_tweet_id  NUMBER(19),
    CONSTRAINT fk_tweet_user
        FOREIGN KEY (user_id) REFERENCES APP_USER (user_id),
    CONSTRAINT fk_tweet_reply
        FOREIGN KEY (reply_to_tweet_id) REFERENCES TWEET (tweet_id) ON DELETE SET NULL,
    CONSTRAINT ck_tweet_not_self_reply
        CHECK (reply_to_tweet_id <> tweet_id)
);

CREATE TABLE HASHTAG (
    hashtag_id     NUMBER(10)          CONSTRAINT pk_hashtag PRIMARY KEY,
    tag_text       VARCHAR2(140 CHAR)  NOT NULL CONSTRAINT uq_hashtag_tag_text UNIQUE,
    first_seen_at  TIMESTAMP,
    CONSTRAINT ck_hashtag_lowercase
        CHECK (tag_text = LOWER(tag_text))
);

CREATE TABLE SENTIMENT_SCORE (
    tweet_id       NUMBER(19)         CONSTRAINT pk_sentiment_score PRIMARY KEY,
    score          NUMBER(4,2)        NOT NULL,
    model_version  VARCHAR2(20 CHAR)  NOT NULL,
    computed_at    TIMESTAMP          NOT NULL,
    CONSTRAINT fk_sentiment_tweet
        FOREIGN KEY (tweet_id) REFERENCES TWEET (tweet_id) ON DELETE CASCADE,
    CONSTRAINT ck_sentiment_score_range
        CHECK (score BETWEEN -1 AND 1)
);

CREATE TABLE TWEET_HASHTAG (
    tweet_id    NUMBER(19)  NOT NULL,
    hashtag_id  NUMBER(10)  NOT NULL,
    tagged_at   TIMESTAMP   NOT NULL,
    CONSTRAINT pk_tweet_hashtag
        PRIMARY KEY (tweet_id, hashtag_id),
    CONSTRAINT fk_th_tweet
        FOREIGN KEY (tweet_id) REFERENCES TWEET (tweet_id) ON DELETE CASCADE,
    CONSTRAINT fk_th_hashtag
        FOREIGN KEY (hashtag_id) REFERENCES HASHTAG (hashtag_id)
);

-- ----------------------------------------------------------------------------
-- Indexes
--
-- Oracle indexes primary keys and unique constraints automatically, but not
-- foreign keys. An unindexed foreign key means full scans when joining from
-- the parent side, and a table lock on the child whenever a parent row is
-- deleted. Every foreign key below therefore leads an index;
-- TWEET_HASHTAG.tweet_id is already covered by that table's primary key.
-- ----------------------------------------------------------------------------

-- Tweets by user: one range scan per user; created_at supports per-user date filters.
CREATE INDEX ix_tweet_user_created ON TWEET (user_id, created_at);

-- Date-range scans (sentiment over time, daily rollups).
CREATE INDEX ix_tweet_created_at ON TWEET (created_at);

-- Supports ON DELETE SET NULL without scanning TWEET.
CREATE INDEX ix_tweet_reply_to ON TWEET (reply_to_tweet_id);

-- Hashtag -> tweets lookups; tweet_id is included so the join is index-only.
CREATE INDEX ix_tweet_hashtag_tag ON TWEET_HASHTAG (hashtag_id, tweet_id);
