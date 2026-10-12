"""Run the Streamlit dashboard headlessly against the loaded database."""

from datetime import date

import pytest
from streamlit.testing.v1 import AppTest

from social_analytics.config import PROJECT_ROOT

pytestmark = pytest.mark.integration


@pytest.fixture
def app(conn):  # `conn` guarantees the schema is built and loaded
    return AppTest.from_file(str(PROJECT_ROOT / "dashboard" / "app.py"), default_timeout=60).run()


def metric(app, label):
    return next(m.value for m in app.metric if m.label == label)


def test_renders_without_errors(app):
    assert not app.exception
    assert not app.error
    assert metric(app, "Tweets") == "10,942"


@pytest.mark.parametrize(
    "period",
    [
        (date(2009, 6, 1), date(2009, 6, 1)),  # a single busy day
        (date(2009, 6, 8), date(2009, 6, 14)),  # a sparse week
        (date(2009, 4, 7), date(2009, 4, 7)),  # no hashtag reaches the leaderboard minimum
    ],
)
def test_handles_narrow_date_ranges(app, period):
    app.date_input[0].set_value(period).run()
    assert not app.exception


def test_hashtag_figures_follow_the_date_filter(app):
    all_time = metric(app, "Active days")
    app.date_input[0].set_value((date(2009, 5, 25), date(2009, 5, 31))).run()
    assert metric(app, "Active days") != all_time


def test_leaderboard_explains_an_empty_result(app):
    app.slider[0].set_value(50).run()
    app.date_input[0].set_value((date(2009, 4, 7), date(2009, 4, 7))).run()
    assert any("No hashtag reaches" in info.value for info in app.info)
