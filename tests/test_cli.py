from datetime import datetime
from decimal import Decimal

import pytest

from social_analytics import cli


def feed_input(monkeypatch, *answers):
    replies = iter(answers)
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(replies))


class TestPrompts:
    def test_ask_int_reprompts_until_valid(self, monkeypatch, capsys):
        feed_input(monkeypatch, "abc", "0", "7")
        assert cli.ask_int("Tweet ID") == 7
        output = capsys.readouterr().out
        assert "whole number" in output
        assert "at least 1" in output

    def test_ask_int_uses_default_on_empty_input(self, monkeypatch):
        feed_input(monkeypatch, "")
        assert cli.ask_int("How many", default=10) == 10

    def test_ask_date_rejects_invalid_dates(self, monkeypatch, capsys):
        feed_input(monkeypatch, "2009-13-01", "June 1", "2009-06-01")
        assert cli.ask_date("Start date") == "2009-06-01"
        assert capsys.readouterr().out.count("Please enter a date") == 2

    def test_ask_requires_a_value_without_default(self, monkeypatch, capsys):
        feed_input(monkeypatch, "  ", "bob")
        assert cli.ask("Username") == "bob"
        assert "required" in capsys.readouterr().out


class TestFormatting:
    @pytest.mark.parametrize(
        ("value", "places", "expected"),
        [
            (None, None, ""),
            (datetime(2009, 6, 1), None, "2009-06-01"),
            (datetime(2009, 6, 1, 13, 5, 59), None, "2009-06-01 13:05"),
            (12345, None, "12,345"),
            (1976990550, None, "1976990550"),  # ids stay unformatted
            (1, 4, "1.0000"),
            (-0.70588, 4, "-0.7059"),
            (Decimal("97.9"), 1, "97.9"),
            ("a  b\nc", None, "a b c"),
        ],
    )
    def test_format_value(self, value, places, expected):
        assert cli.format_value(value, places) == expected

    def test_long_text_is_truncated(self):
        text = cli.format_value("x" * 200)
        assert len(text) == cli.MAX_TEXT_WIDTH
        assert text.endswith("…")

    def test_decimal_places_cover_the_most_precise_value(self):
        assert cli.decimal_places([1, -0.5, 0.7059, None]) == 4
        assert cli.decimal_places([100, 14.7]) == 1
        assert cli.decimal_places([1, 2, None]) is None

    def test_print_table_aligns_columns(self, capsys):
        cli.print_table(["tag", "uses", "net"], [("fb", 132, 0.25), ("e3", 66, 1)])
        lines = capsys.readouterr().out.strip().splitlines()
        assert lines[0].split() == ["tag", "uses", "net"]
        assert lines[2].split() == ["fb", "132", "0.25"]
        assert lines[3].split() == ["e3", "66", "1.00"]
        assert lines[-1] == "2 rows"

    def test_print_table_caps_long_results(self, capsys):
        cli.print_table(["n"], [(i,) for i in range(cli.MAX_ROWS + 5)])
        assert f"(showing first {cli.MAX_ROWS})" in capsys.readouterr().out

    def test_print_table_reports_empty_results(self, capsys):
        cli.print_table(["n"], [])
        assert "No results found." in capsys.readouterr().out


def test_every_menu_option_names_a_catalog_query():
    from social_analytics import queries

    for _label, query_name, _prompt in cli.MENU.values():
        queries.get(query_name)
