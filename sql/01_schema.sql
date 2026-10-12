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
    user_id NUMBER PRIMARY KEY,
    username VARCHAR2(50) NOT NULL,
    email VARCHAR2(100) NOT NULL UNIQUE,
    display_name VARCHAR2(100),
    location VARCHAR2(100),
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE TWEET (
    tweet_id NUMBER PRIMARY KEY,
    user_id NUMBER NOT NULL,
    tweet_text VARCHAR2(280) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    lang VARCHAR2(10),
    reply_to_tweet_id NUMBER,
    CONSTRAINT fk_tweet_user
        FOREIGN KEY (user_id) REFERENCES APP_USER(user_id),
    CONSTRAINT fk_tweet_reply
        FOREIGN KEY (reply_to_tweet_id) REFERENCES TWEET(tweet_id)
);

CREATE TABLE HASHTAG (
    hashtag_id NUMBER PRIMARY KEY,
    tag_text VARCHAR2(100) NOT NULL UNIQUE,
    first_seen_at TIMESTAMP
);

CREATE TABLE SENTIMENT_SCORE (
    tweet_id NUMBER PRIMARY KEY,
    score NUMBER(4,2) NOT NULL,
    model_version VARCHAR2(20),
    computed_at TIMESTAMP NOT NULL,
    CONSTRAINT fk_sentiment_tweet
        FOREIGN KEY (tweet_id) REFERENCES TWEET(tweet_id)
);

CREATE TABLE TWEET_HASHTAG (
    tweet_id NUMBER NOT NULL,
    hashtag_id NUMBER NOT NULL,
    tagged_at TIMESTAMP NOT NULL,
    CONSTRAINT pk_tweet_hashtag
        PRIMARY KEY (tweet_id, hashtag_id),
    CONSTRAINT fk_th_tweet
        FOREIGN KEY (tweet_id) REFERENCES TWEET(tweet_id),
    CONSTRAINT fk_th_hashtag
        FOREIGN KEY (hashtag_id) REFERENCES HASHTAG(hashtag_id)
);
