"""Streamlit dashboard for the tweet analytics database.

    streamlit run dashboard/app.py

Every figure on the page comes from a named query in sql/queries.sql, the
same catalog the CLI and tests use.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import altair as alt
import oracledb
import pandas as pd
import streamlit as st

# `streamlit run` puts this file's folder on sys.path, not the project root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from social_analytics import queries  # noqa: E402
from social_analytics.db import create_pool, fetch_df  # noqa: E402

st.set_page_config(page_title="Tweet Analytics", page_icon=":material/monitoring:", layout="wide")

# Validated chart colors (light / dark steps of the same hues). Single-series
# charts use blue; polarity uses the blue <-> red diverging pair.
PALETTES = {
    "light": {"series": "#2a78d6", "positive": "#2a78d6", "negative": "#e34948",
              "baseline": "#c3c2b7", "ink": "#52514e", "surface": "#ffffff"},
    "dark": {"series": "#3987e5", "positive": "#3987e5", "negative": "#e66767",
             "baseline": "#383835", "ink": "#c3c2b7", "surface": "#0e1117"},
}  # fmt: skip


def colors() -> dict[str, str]:
    theme = getattr(st.context, "theme", None)
    return PALETTES["dark" if theme is not None and theme.type == "dark" else "light"]


# --------------------------------------------------------------------------
# Data access
# --------------------------------------------------------------------------


@st.cache_resource(show_spinner=False)
def pool() -> oracledb.ConnectionPool:
    return create_pool()


@st.cache_data(ttl=600, show_spinner=False)
def run(query_name: str, **params) -> pd.DataFrame:
    with pool().acquire() as conn:
        return fetch_df(conn, queries.get(query_name).sql, params)


def iso(day: date) -> str:
    return day.isoformat()


def within(df: pd.DataFrame, column: str, first: date, last: date) -> pd.DataFrame:
    """Rows whose timestamp column falls on a day in [first, last]."""
    return df[df[column].dt.date.between(first, last)]


# --------------------------------------------------------------------------
# Chart builders (thin marks, hairline chrome, hover tooltips)
# --------------------------------------------------------------------------

DATE_AXIS = alt.Axis(format="%b %d", labelAngle=0, title=None, tickCount=8)


def daily_columns(df: pd.DataFrame, y: str, y_title: str, domain: list[str], tooltip: list):
    days = (pd.Timestamp(domain[1]) - pd.Timestamp(domain[0])).days + 1
    return (
        alt.Chart(df)
        .mark_bar(color=colors()["series"], cornerRadiusEnd=4, size=max(2, min(24, 640 // days)))
        .encode(
            x=alt.X("activity_date:T", scale=alt.Scale(domain=domain), axis=DATE_AXIS),
            y=alt.Y(f"{y}:Q", title=y_title, axis=alt.Axis(format=",.0f")),
            tooltip=tooltip,
        )
        .properties(height=220)
    )


def sentiment_line(df: pd.DataFrame, y: str, domain: list[str], tooltip: list):
    """2px line on a fixed -1..1 scale with a zero baseline and a hover crosshair."""
    c = colors()
    nearest = alt.selection_point(
        nearest=True, on="pointerover", fields=["activity_date"], empty=False, clear="pointerout"
    )
    base = alt.Chart(df).encode(
        x=alt.X("activity_date:T", scale=alt.Scale(domain=domain), axis=DATE_AXIS),
        y=alt.Y(f"{y}:Q", title="Net sentiment", scale=alt.Scale(domain=[-1, 1])),
    )
    zero = alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(color=c["baseline"]).encode(y="y:Q")
    line = base.mark_line(color=c["series"], strokeWidth=2, strokeCap="round", strokeJoin="round")
    hover_targets = base.mark_point(size=400, opacity=0).add_params(nearest)
    rule = (
        base.mark_rule(color=c["baseline"])
        .encode(y=alt.value(0), y2=alt.value(220), tooltip=tooltip)
        .transform_filter(nearest)
    )
    dot = base.mark_point(
        filled=True, size=80, color=c["series"], stroke=c["surface"], strokeWidth=2, opacity=1
    ).transform_filter(nearest)
    return alt.layer(zero, line, hover_targets, rule, dot).properties(height=220)


def ranked_bars(df: pd.DataFrame, label: str, value: str, value_title: str, tooltip: list):
    """Horizontal single-series bars, longest first, with the value at each tip."""
    c = colors()
    order = df[label].tolist()
    base = alt.Chart(df).encode(
        y=alt.Y(f"{label}:N", sort=order, title=None, axis=alt.Axis(labelLimit=160)),
        x=alt.X(f"{value}:Q", title=value_title, axis=alt.Axis(format=",.0f")),
        tooltip=tooltip,
    )
    bars = base.mark_bar(color=c["series"], cornerRadiusEnd=4, size=16)
    labels = base.mark_text(align="left", dx=4, color=c["ink"]).encode(text=f"{value}:Q")
    return (bars + labels).properties(height=alt.Step(28))


def diverging_bars(df: pd.DataFrame):
    """Net sentiment per hashtag, blue right of zero and red left of it."""
    c = colors()
    order = df.sort_values("net_sentiment", ascending=False)["label"].tolist()
    tooltip = [
        alt.Tooltip("tag_text:N", title="Hashtag"),
        alt.Tooltip("net_sentiment:Q", title="Net sentiment", format="+.2f"),
        alt.Tooltip("pct_positive:Q", title="% positive", format=".1f"),
        alt.Tooltip("tweet_count:Q", title="Tweets", format=","),
    ]
    color = alt.Color(
        "side:N",
        scale=alt.Scale(
            domain=["Most positive", "Most negative"], range=[c["positive"], c["negative"]]
        ),
        legend=alt.Legend(title=None, orient="top"),
    )
    base = alt.Chart(df).encode(
        y=alt.Y("label:N", sort=order, title=None, axis=alt.Axis(labelLimit=200)),
        x=alt.X(
            "net_sentiment:Q",
            title="Net sentiment (−1 all negative, +1 all positive)",
            scale=alt.Scale(domain=[-1, 1]),
            axis=alt.Axis(values=[-1, -0.5, 0, 0.5, 1], format=".1f"),
        ),
        color=color,
        tooltip=tooltip,
    )
    # Round only the end away from zero: right for positive bars, left for negative.
    positive = base.transform_filter(alt.datum.net_sentiment >= 0).mark_bar(
        size=16, cornerRadiusTopRight=4, cornerRadiusBottomRight=4
    )
    negative = base.transform_filter(alt.datum.net_sentiment < 0).mark_bar(
        size=16, cornerRadiusTopLeft=4, cornerRadiusBottomLeft=4
    )
    zero = alt.Chart(pd.DataFrame({"x": [0]})).mark_rule(color=c["baseline"]).encode(x="x:Q")
    return alt.layer(positive, negative, zero).properties(height=alt.Step(28))


def show_chart(chart) -> None:
    st.altair_chart(chart, width="stretch")


def table_view(df: pd.DataFrame, label: str = "Table view") -> None:
    with st.expander(label):
        st.dataframe(df, hide_index=True)


# --------------------------------------------------------------------------
# Page
# --------------------------------------------------------------------------

try:
    overview = run("dataset_overview").iloc[0]
except (oracledb.Error, RuntimeError) as error:
    st.error(
        f"Could not reach the database: {error}\n\n"
        "Start it with `docker compose up -d`, then load data with "
        "`python -m social_analytics init-db` and `python -m social_analytics load`."
    )
    st.stop()

first_day, last_day = overview["first_day"].date(), overview["last_day"].date()

st.title("Tweet Analytics")
st.caption(
    f"{overview['tweets']:,} tweets from the Sentiment140 corpus, {first_day:%B} {first_day.day} "
    f"to {last_day:%B} {last_day.day}, {last_day.year}, stored in Oracle and queried live. "
    "Sentiment labels come from emoticons in the original tweets, so treat them as noisy."
)

# One filter row scopes every chart on the page.
filter_col, _ = st.columns([2, 3])
with filter_col:
    picked = st.date_input(
        "Date range",
        value=(first_day, last_day),
        min_value=first_day,
        max_value=last_day,
        format="YYYY-MM-DD",
    )
start, end = (picked[0], picked[-1]) if picked else (first_day, last_day)
period = {"start_date": iso(start), "end_date": iso(end)}
x_domain = [iso(start), iso(end + timedelta(days=1))]

summary = run("period_summary", **period).iloc[0]
activity = run("daily_activity", **period)

tiles = st.columns(4)
tiles[0].metric(
    "Tweets",
    f"{int(summary['tweets']):,}",
    border=True,
)
tiles[1].metric("Authors", f"{int(summary['users']):,}", border=True)
tiles[2].metric("Hashtags in use", f"{int(summary['hashtags']):,}", border=True)
tiles[3].metric(
    "Positive tweets",
    f"{summary['pct_positive'] or 0:.1f}%",
    help="Share of scored tweets labeled positive.",
    border=True,
)

trends_tab, explorer_tab, leaderboard_tab, lookup_tab = st.tabs(
    ["Trends", "Hashtag explorer", "Sentiment leaderboard", "Lookup"]
)

# ----- Trends --------------------------------------------------------------
with trends_tab:
    volume_tooltip = [
        alt.Tooltip("activity_date:T", title="Day", format="%a %b %d"),
        alt.Tooltip("tweet_count:Q", title="Tweets", format=","),
    ]
    sentiment_tooltip = [
        alt.Tooltip("activity_date:T", title="Day", format="%a %b %d"),
        alt.Tooltip("net_sentiment_7d:Q", title="7-day net sentiment", format="+.2f"),
        alt.Tooltip("net_sentiment:Q", title="That day", format="+.2f"),
        alt.Tooltip("tweet_count:Q", title="Tweets that day", format=","),
    ]
    st.subheader("Daily tweet volume")
    show_chart(daily_columns(activity, "tweet_count", "Tweets", x_domain, volume_tooltip))
    st.subheader("Net sentiment, 7-day rolling")
    st.caption("Tweet-weighted over 7 calendar days; −1 is all negative, +1 all positive.")
    show_chart(sentiment_line(activity, "net_sentiment_7d", x_domain, sentiment_tooltip))
    table_view(activity)

    left, right = st.columns(2, gap="large")
    with left:
        st.subheader("Top hashtags")
        top = run("top_hashtags_in_range", **period, row_limit=10)
        top["hashtag"] = "#" + top["tag_text"]
        show_chart(
            ranked_bars(
                top,
                "hashtag",
                "tweet_count",
                "Tweets",
                [
                    alt.Tooltip("hashtag:N", title="Hashtag"),
                    alt.Tooltip("tweet_count:Q", title="Tweets", format=","),
                    alt.Tooltip("net_sentiment:Q", title="Net sentiment", format="+.2f"),
                ],
            )
        )
    with right:
        st.subheader("Trending week over week")
        weekly = (
            activity.assign(week=activity["activity_date"].dt.to_period("W-SUN").dt.start_time)
            .groupby("week")["tweet_count"]
            .sum()
        )
        weeks = list(weekly.index.date)
        if weeks:
            busiest = weeks.index(weekly.idxmax().date())
            week = st.selectbox(
                "Week starting",
                weeks,
                index=busiest,
                format_func=lambda d: f"{d:%b %d, %Y}",
            )
            trending = run("trending_hashtags", week_of=iso(week), top_n=10)
            trending["growth"] = trending["growth_pct"].map(
                lambda pct: "new" if pd.isna(pct) else f"{pct:+,.0f}%"
            )
            st.dataframe(
                trending[["tag_text", "uses", "prev_week_uses", "change", "growth"]],
                hide_index=True,
                column_config={
                    "tag_text": st.column_config.TextColumn("Hashtag"),
                    "uses": st.column_config.NumberColumn("This week"),
                    "prev_week_uses": st.column_config.NumberColumn("Last week"),
                    "change": st.column_config.NumberColumn("Change", format="%+d"),
                    "growth": st.column_config.TextColumn("Growth"),
                },
            )
            st.caption("“new” means the hashtag was not used the week before.")

# ----- Hashtag explorer ----------------------------------------------------
with explorer_tab:
    popular = run("popular_hashtags", min_tweets=10)
    tags = popular["tag_text"].tolist()
    tag = st.selectbox(
        "Hashtag",
        tags,
        index=tags.index("followfriday") if "followfriday" in tags else 0,
        format_func=lambda t: f"#{t}",
    )
    stats = run("hashtag_period_summary", hashtag=tag, **period).iloc[0]
    used = stats["tweet_count"] > 0
    cols = st.columns(4)
    cols[0].metric("Tweets", f"{int(stats['tweet_count']):,}", border=True)
    cols[1].metric("Net sentiment", f"{stats['net_sentiment']:+.2f}" if used else "–", border=True)
    cols[2].metric("Positive", f"{stats['pct_positive']:.1f}%" if used else "–", border=True)
    cols[3].metric("Active days", f"{int(stats['active_days']):,}", border=True)

    trend = run("hashtag_daily_trend", hashtag=tag).rename(columns={"stat_date": "activity_date"})
    trend = within(trend, "activity_date", start, end)
    st.subheader(f"Daily uses of #{tag}")
    show_chart(daily_columns(trend, "tweet_count", "Tweets", x_domain, volume_tooltip))
    st.subheader(f"Net sentiment of #{tag}, 7-day rolling")
    show_chart(sentiment_line(trend, "net_sentiment_7d", x_domain, sentiment_tooltip))
    table_view(trend)

    st.subheader("Recent tweets")
    tweets = run("tweets_with_hashtag", hashtag=tag)
    tweets = within(tweets, "created_at", start, end)
    st.dataframe(
        tweets[["created_at", "tweet_text", "score"]].head(25),
        hide_index=True,
        column_config={
            "created_at": st.column_config.DatetimeColumn("Posted (UTC)", format="MMM D, HH:mm"),
            "tweet_text": st.column_config.TextColumn("Tweet", width="large"),
            "score": st.column_config.NumberColumn("Label", format="%+d"),
        },
    )

# ----- Sentiment leaderboard -----------------------------------------------
with leaderboard_tab:
    controls = st.columns([1, 1, 2])
    min_tweets = controls[0].slider("Minimum tweets per hashtag", 5, 50, 10)
    per_side = controls[1].slider("Hashtags per side", 3, 15, 8)
    extremes = run("hashtag_sentiment_extremes", **period, min_tweets=min_tweets, top_n=per_side)
    if extremes.empty:
        st.info("No hashtag reaches that many tweets in the selected range.")
    else:
        extremes["side"] = extremes["side"].map(
            {"positive": "Most positive", "negative": "Most negative"}
        )
        # A hashtag can rank on both sides when few qualify; show it once.
        extremes = extremes.drop_duplicates("tag_text")
        extremes["label"] = "#" + extremes["tag_text"]
        show_chart(diverging_bars(extremes))
        table_view(extremes.drop(columns=["label"]))

# ----- Lookup ----------------------------------------------------------------
with lookup_tab:
    mode = st.segmented_control(
        "Look up", ["Tweets by user", "Hashtags in a tweet", "Tweets with a hashtag"],
        default="Tweets by user",
    )  # fmt: skip
    if mode == "Tweets by user":
        username = st.text_input("Username", placeholder="e.g. thisgoeshere")
        if username:
            st.dataframe(run("tweets_by_user", username=username), hide_index=True)
    elif mode == "Hashtags in a tweet":
        tweet_id = st.text_input("Tweet ID", placeholder="e.g. 1976990550")
        if tweet_id and not tweet_id.strip().isdigit():
            st.warning("A tweet ID is a whole number.")
        elif tweet_id:
            st.dataframe(run("hashtags_for_tweet", tweet_id=int(tweet_id)), hide_index=True)
    elif mode == "Tweets with a hashtag":
        hashtag = st.text_input("Hashtag", placeholder="e.g. #e3")
        if hashtag:
            st.dataframe(run("tweets_with_hashtag", hashtag=hashtag), hide_index=True)

st.divider()
st.caption(
    "Data: Sentiment140 (Go, Bhayani & Huang, 2009). Built with Oracle Database Free, "
    "python-oracledb, and Streamlit."
)
