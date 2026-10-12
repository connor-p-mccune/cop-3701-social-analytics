**Project Name:** Social Analytics Database  
**Database Owner:** Connor McCune  
**Team Member:** Johnathan Nguyen

## Features
### Feature 1: View all tweets by a selected user  
**Description:** This feature allows the user to enter a username and view all tweets posted by that user, sorted by most recent first.

**SQL Query:**
```sql
SELECT u.username,
       t.tweet_id,
       t.tweet_text,
       t.created_at
FROM APP_USER u
JOIN TWEET t
    ON u.user_id = t.user_id
WHERE u.username = :username
ORDER BY t.created_at DESC;
```

### Feature 2: View all hashtags used in a selected tweet
**Description:** This feature allows the user to enter a tweet ID and see every hashtag attached to that tweet.

**SQL Query:**
```sql
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
```

### Feature 3: Find all tweets containing a selected hashtag  
**Description:** This feature allows the user to enter a hashtag and retrieve all tweets that use it, sorted by most recent first.

**SQL Query:**
```sql
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
```

### Feature 4: View tweet sentiment scores in a date range
**Description:** This feature allows the user to enter a start date and end date to see tweets and their sentiment scores during that time period.

**SQL Query:**
```sql
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
```

### Feature 5: Show the top hashtags by usage count
**Description:** This feature shows the most frequently used hashtags in the database and ranks them by total usage.

**SQL Query:**
```sql
SELECT h.tag_text,
       COUNT(*) AS usage_count
FROM HASHTAG h
JOIN TWEET_HASHTAG th
    ON h.hashtag_id = th.hashtag_id
GROUP BY h.tag_text
ORDER BY usage_count DESC, h.tag_text;
```