# Features

Every feature is one named query in [`sql/queries.sql`](../sql/queries.sql). The
CLI (`python -m social_analytics cli`), the dashboard, and the integration
tests all run exactly that SQL. The examples below are real results from the
sample data in `data/`, printed by the CLI.

| # | Feature | Query name |
|---|---|---|
| 1 | All tweets by a user | `tweets_by_user` |
| 2 | Hashtags used in a tweet | `hashtags_for_tweet` |
| 3 | Tweets that use a hashtag | `tweets_with_hashtag` |
| 4 | Sentiment scores in a date range | `sentiment_in_date_range` |
| 5 | Most-used hashtags | `top_hashtags` |
| 6 | Each day's top hashtags | `daily_top_hashtags` |
| 7 | Sentiment trend for one hashtag | `hashtag_daily_trend` |
| 8 | Most positive and negative hashtags | `hashtag_sentiment_extremes` |
| 9 | Trending hashtags, week over week | `trending_hashtags` |

Features 1–5 are the original lookup features from the course project.
Features 6–9 deliver the trend analytics the project set out to support, and
they read the daily rollup table maintained by `REFRESH_HASHTAG_STATS` (see
[database-design.md](database-design.md#analytics-layer)).

---

## Lookups

### 1. All tweets by a user

Enter a username and get that user's tweets, newest first. The match ignores
case and a leading `@`, as Twitter handles do. `LOWER(username)` is backed by a
function-based unique index, so the lookup is an index unique scan followed by
a range scan on `(user_id, created_at)`.

```text
username    tweet_id  tweet_text                                                              created_at
--------  ----------  ----------------------------------------------------------------------  ----------------
daynah    2071914965  @danielbru Let's trade places.. Have fun at #WWDC tomorrow!             2009-06-08 03:06
daynah    2001616153  @Lotay #wordcamp SF was a ton of fun, as was @googleio.                 2009-06-02 08:28
daynah    1988957848  @davecurlee it was great to finally meet you IRL too! Hope to see you…  2009-06-01 06:53
daynah    1988840119  @TechFrog I saw @Calilewis @nealcampbell and @davecurlee at #wordcamp…  2009-06-01 06:31
```

### 2. Hashtags used in a tweet

Enter a tweet ID and see every hashtag attached to it. The many-to-many
relationship is resolved through the `TWEET_HASHTAG` associative table.

```text
  tweet_id  tweet_text                                                              tag_text
----------  ----------------------------------------------------------------------  ---------
1556142853  #Microsoft will release #Windows7 #RC on May 5, 2009. I guess I alrea…  microsoft
1556142853  #Microsoft will release #Windows7 #RC on May 5, 2009. I guess I alrea…  rc
1556142853  #Microsoft will release #Windows7 #RC on May 5, 2009. I guess I alrea…  windows7
```

### 3. Tweets that use a hashtag

Enter a hashtag (`#E3`, `e3`, and `#e3` are equivalent) and get every tweet
that uses it, newest first, with its sentiment label.

```text
tag_text    tweet_id  tweet_text                                                              score  created_at
--------  ----------  ----------------------------------------------------------------------  -----  ----------------
e3        2064632937  @alexiatsotsis Well, mine too, don't be so possessive After #e3, I th…      1  2009-06-07 13:47
e3        2060492082  #e3 was this week, #WWDC is next week, the #NHL finals are happening …      1  2009-06-07 02:00
e3        2049916614  Can't believe E3 is over for another year. Feels like it's over befor…     -1  2009-06-06 00:43
e3        2047747379  Yes! Second Mass Effect DLC (for original game) is coming! http://tin…      1  2009-06-05 21:07
e3        2031402964  Sitting in IGN Editorial War room -- stole Ferret's computer to Tweet…     -1  2009-06-04 16:46

(first 5 of 66 rows)
```

### 4. Sentiment scores in a date range

Enter start and end dates (inclusive, `YYYY-MM-DD`). The query uses the
half-open range `[start, end + 1 day)` with explicit `TO_DATE` formats, so the
end date covers its whole day and the result never depends on session NLS
settings.

```text
  tweet_id  tweet_text                                                              score  model_version  created_at
----------  ----------------------------------------------------------------------  -----  -------------  ----------------
2169489380  @mysugarisraw im glad some one is having a nice sunday! I miss family…     -1  sentiment140   2009-06-14 21:35
2169467622  Been trying to work on #PhD paper all day, but too many distractions …     -1  sentiment140   2009-06-14 21:33
2169458101  I swear I just had th best nap ever. And Olgas has really good bread        1  sentiment140   2009-06-14 21:32
```

### 5. Most-used hashtags

The top N hashtags by number of tweets (`FETCH FIRST :row_limit ROWS ONLY`).

```text
tag_text      usage_count
------------  -----------
followfriday          658
fb                    336
ff                    246
squarespace           111
musicmonday           110
asot400                87
iremember              76
myweakness             73
bgt                    69
e3                     66
```

---

## Trend analytics

### 6. Each day's top hashtags

The "top hashtags today" leaderboard for every day in a range.
`ROW_NUMBER() OVER (PARTITION BY stat_date ORDER BY tweet_count DESC, tag_text)`
ranks hashtags within each day, with a deterministic tie-break.

Over May 29–June 1, 2009, the results include #followfriday on a Friday, the
Britain's Got Talent final (#bgt) on May 30, and #musicmonday plus E3's
opening press conferences on June 1:

```text
stat_date   daily_rank  tag_text       tweet_count
----------  ----------  -------------  -----------
2009-05-29           1  followfriday           180
2009-05-29           2  ff                      57
2009-05-29           3  fb                      14
2009-05-30           1  myweakness              72
2009-05-30           2  followfriday            59
2009-05-30           3  bgt                     49
2009-05-31           1  andyhurleyday           46
2009-05-31           2  fb                      31
2009-05-31           3  mmwanted                21
2009-06-01           1  musicmonday             40
2009-06-01           2  fb                      33
2009-06-01           3  e3                      28
```

### 7. Sentiment trend for one hashtag

Daily usage and net sentiment for a hashtag, plus a 7-day rolling value. The
window is `RANGE BETWEEN 6 PRECEDING AND CURRENT ROW` over dates, so it always
spans seven calendar days even where the corpus has gaps, and each day is
weighted by its tweet count. #musicmonday spikes on Mondays (May 18, June 1,
June 15):

```text
stat_date   tweet_count  positive_count  negative_count  net_sentiment  net_sentiment_7d
----------  -----------  --------------  --------------  -------------  ----------------
2009-05-04            2               2               0         1.0000            1.0000
2009-05-12            1               1               0         1.0000            1.0000
2009-05-18           23              19               4         0.6522            0.6667
2009-06-01           40              38               2         0.9000            0.9000
2009-06-02            6               5               1         0.6667            0.8696
2009-06-15           30              29               1         0.9333            0.9333
2009-06-16            8               8               0         1.0000            0.9474
```

### 8. Most positive and negative hashtags

The N most positive and most negative hashtags in a date window, among
hashtags with at least a minimum number of tweets. Two `ROW_NUMBER()` windows
rank the same aggregated rows in opposite directions. Sentiment140's labels
come from emoticons, so some results are noisy: #annoying scores as
positive.

```text
side      side_rank  tag_text          tweet_count  net_sentiment  pct_positive
--------  ---------  ----------------  -----------  -------------  ------------
positive          1  robotpickuplines           13         1.0000         100.0
positive          2  annoying                   10         1.0000         100.0
positive          3  writechat                  10         1.0000         100.0
positive          4  followfriday              430         0.9581          97.9
positive          5  follow                     20         0.9000          95.0
negative          1  fail                       34        -0.7059          14.7
negative          2  javaone                    12        -0.5000          25.0
negative          3  pens                       15        -0.4667          26.7
negative          4  ontd                       19        -0.3684          31.6
negative          5  twpp                       10        -0.2000          40.0
```

### 9. Trending hashtags, week over week

Hashtags whose usage grew most in an ISO week (Monday–Sunday) compared with
the week before. `LAG()` finds each hashtag's previous active week. If that
week is not the immediately preceding one, the hashtag counts as unused last
week, and `growth_pct` is left empty because growth from zero is undefined.

In the week of June 1, 2009, E3 dominates. Further down the same list, #xboxe3
grew 1,350% and #eu09 (the European Parliament election, June 4–7) grew
1,150%.

```text
tag_text     week_start  uses  prev_week_uses  change  growth_pct
-----------  ----------  ----  --------------  ------  ----------
e3           2009-06-01    66               0      66
fb           2009-06-01   132              78      54          69
musicmonday  2009-06-01    46               0      46
```

---

## Supporting queries

These power the dashboard's headline figures and pickers:

| Query | Returns |
|---|---|
| `dataset_overview` | Counts, percent positive, and date span of the loaded data |
| `period_summary` | Tweets, authors, hashtags in use, and percent positive for a date range |
| `daily_activity` | Rows of `v_daily_activity` for a date range |
| `top_hashtags_in_range` | Most-used hashtags in a range, with net sentiment |
| `popular_hashtags` | Lifetime stats for hashtags above a usage threshold |
| `hashtag_period_summary` | One hashtag's usage and sentiment in a range |

## Credits

Features 1–5 and the original menu-driven CLI were designed and built by
Johnathan Nguyen. The database, ETL, analytics layer (Features 6–9),
dashboard, and tests are by Connor McCune.
