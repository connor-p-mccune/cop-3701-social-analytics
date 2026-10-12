-- Feature 1: Views all the tweets by a selected user
SELECT u.username,
       t.tweet_id,
       t.tweet_text,
       t.created_at
FROM APP_USER u
JOIN TWEET t
    ON u.user_id = t.user_id
WHERE u.username = :username
ORDER BY t.created_at DESC;

-- Feature 2: Views all the hashtags used in a selected tweet
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

-- Feature 3: Finds all the tweets containing a selected hashtag
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

-- Feature 4: Views tweet sentiment scores in a date range
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

-- Feature 5: Shows the top hashtags by usage count
SELECT h.tag_text,
       COUNT(*) AS usage_count
FROM HASHTAG h
JOIN TWEET_HASHTAG th
    ON h.hashtag_id = th.hashtag_id
GROUP BY h.tag_text
ORDER BY usage_count DESC, h.tag_text;