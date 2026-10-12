import pytest

from social_analytics.sql_runner import schema_scripts, split_statements, strip_line_comment


def test_splits_plain_statements_and_drops_terminators():
    script = """
    -- leading comment;
    CREATE TABLE a (id NUMBER);

    INSERT INTO a VALUES (1); -- trailing comment
    """
    assert split_statements(script) == [
        "CREATE TABLE a (id NUMBER)",
        "INSERT INTO a VALUES (1)",
    ]


def test_keeps_plsql_blocks_whole_until_slash():
    script = """
BEGIN
   FOR t IN (SELECT 1 FROM dual) LOOP
      NULL;
   END LOOP;
END;
/

CREATE OR REPLACE PROCEDURE p (x IN NUMBER) AS
BEGIN
   UPDATE a SET id = x;
END p;
/
SELECT 1 FROM dual;
"""
    statements = split_statements(script)
    assert len(statements) == 3
    assert statements[0].startswith("BEGIN") and statements[0].endswith("END;")
    assert statements[1].startswith("CREATE OR REPLACE PROCEDURE")
    assert statements[1].endswith("END p;")
    assert statements[2] == "SELECT 1 FROM dual"


def test_semicolons_and_dashes_inside_strings_are_not_terminators():
    script = "COMMENT ON TABLE a IS 'one; two -- three';\nSELECT 1 FROM dual;"
    assert split_statements(script) == [
        "COMMENT ON TABLE a IS 'one; two -- three'",
        "SELECT 1 FROM dual",
    ]


def test_strip_line_comment_respects_string_literals():
    assert strip_line_comment("SELECT '--x' FROM dual -- note") == "SELECT '--x' FROM dual "
    assert strip_line_comment("-- whole line") == ""


def test_unterminated_statement_is_an_error():
    with pytest.raises(ValueError, match="Unterminated"):
        split_statements("SELECT 1 FROM dual")


def test_project_scripts_split_cleanly():
    scripts = {path.name: split_statements(path.read_text()) for path in schema_scripts()}
    assert list(scripts) == ["01_schema.sql", "02_analytics.sql"]
    for statements in scripts.values():
        assert statements
        assert all(not s.rstrip().endswith("/") for s in statements)
    procedures = [s for s in scripts["02_analytics.sql"] if "PROCEDURE" in s.split("\n")[0]]
    assert len(procedures) == 1
    assert procedures[0].endswith("END refresh_hashtag_stats;")
