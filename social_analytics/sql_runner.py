"""Run SQL*Plus-style scripts from Python.

The scripts in sql/ stay runnable in SQL*Plus, SQLcl, and SQL Developer, so
they follow those tools' conventions:

* plain SQL statements end with a semicolon at the end of a line;
* PL/SQL blocks (BEGIN/DECLARE and CREATE PROCEDURE/FUNCTION/TRIGGER/...)
  keep their inner semicolons and end with a line containing only "/".

Usage:
    python -m social_analytics init-db
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import oracledb

from .config import SQL_DIR
from .db import connect

PLSQL_START = re.compile(
    r"^\s*(BEGIN|DECLARE|CREATE\s+(OR\s+REPLACE\s+)?"
    r"((NON)?EDITIONABLE\s+)?(PROCEDURE|FUNCTION|PACKAGE|TRIGGER|TYPE)\b)",
    re.IGNORECASE,
)


def strip_line_comment(line: str) -> str:
    """Remove a trailing `-- comment` that is not inside a string literal."""
    in_string = False
    for i, ch in enumerate(line):
        if ch == "'":
            in_string = not in_string
        elif ch == "-" and not in_string and line.startswith("--", i):
            return line[:i]
    return line


def split_statements(script: str) -> list[str]:
    """Split a script into executable statements (without terminators)."""
    statements: list[str] = []
    buffer: list[str] = []
    is_plsql = False

    def flush(text: str) -> None:
        if text.strip():
            statements.append(text.strip())
        buffer.clear()

    for line in script.splitlines():
        code = strip_line_comment(line).rstrip()
        if not buffer:
            if not code.strip():
                continue  # blank or comment-only line between statements
            is_plsql = bool(PLSQL_START.match(code))

        if code.strip() == "/":
            flush("\n".join(buffer))
            continue

        buffer.append(line)
        if not is_plsql and code.endswith(";"):
            buffer[-1] = code[:-1]  # drop the terminator and any trailing comment
            flush("\n".join(buffer))

    if any(strip_line_comment(line).strip() for line in buffer):
        raise ValueError(f"Unterminated statement at end of script:\n{chr(10).join(buffer)}")
    return statements


def run_script(conn: oracledb.Connection, path: Path) -> int:
    """Execute every statement in `path`; return how many ran."""
    statements = split_statements(path.read_text(encoding="utf-8"))
    with conn.cursor() as cursor:
        for statement in statements:
            cursor.execute(statement)
            # PL/SQL that compiles with errors is created but invalid; python-oracledb
            # reports that as a warning rather than an exception.
            if cursor.warning:
                raise RuntimeError(f"{path.name}: {cursor.warning}\n{statement[:200]}")
    conn.commit()
    return len(statements)


def schema_scripts() -> list[Path]:
    """Numbered setup scripts (01_schema.sql, 02_..., ...) in run order."""
    return sorted(SQL_DIR.glob("[0-9][0-9]_*.sql"))


def main(argv: list[str] | None = None) -> None:
    argparse.ArgumentParser(
        prog="python -m social_analytics init-db",
        description="Create the schema and analytics objects. Drops existing tables and data.",
    ).parse_args(argv)
    with connect() as conn:
        for path in schema_scripts():
            print(f"{path.name}: {run_script(conn, path)} statements")
