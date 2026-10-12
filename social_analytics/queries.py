"""Load the named queries in sql/queries.sql.

The SQL file is the single source of truth: the CLI, dashboard, tests, and
docs all refer to queries by name instead of keeping their own copies.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from .config import SQL_DIR

QUERIES_FILE = SQL_DIR / "queries.sql"

NAME_LINE = re.compile(r"^-- name: (\w+)[ \t]*$", re.MULTILINE)
STRING_LITERAL = re.compile(r"'(?:[^']|'')*'")
BIND_VARIABLE = re.compile(r"(?<![:\w]):([a-zA-Z]\w*)")


@dataclass(frozen=True)
class Query:
    name: str
    description: str
    sql: str

    @property
    def binds(self) -> tuple[str, ...]:
        """Bind variable names in order of first use (string literals ignored)."""
        code = STRING_LITERAL.sub("''", self.sql)
        return tuple(dict.fromkeys(BIND_VARIABLE.findall(code)))


def parse_queries(text: str) -> dict[str, Query]:
    """Parse catalog text into {name: Query}."""
    parts = NAME_LINE.split(text)
    queries: dict[str, Query] = {}
    # parts = [preamble, name1, body1, name2, body2, ...]
    for name, body in zip(parts[1::2], parts[2::2], strict=True):
        if name in queries:
            raise ValueError(f"duplicate query name: {name}")
        lines = body.strip().splitlines()
        description = []
        while lines and lines[0].startswith("--"):
            description.append(lines.pop(0).removeprefix("--").strip())
        # Comments after the statement (e.g. a section header) belong to no query.
        while lines and (not lines[-1].strip() or lines[-1].lstrip().startswith("--")):
            lines.pop()
        sql = "\n".join(lines).strip()
        if not sql.endswith(";"):
            raise ValueError(f"query {name!r} must end with a semicolon")
        sql = sql[:-1].rstrip()
        if not sql:
            raise ValueError(f"query {name!r} has no SQL")
        queries[name] = Query(name, " ".join(description), sql)
    return queries


@cache
def catalog(path: Path = QUERIES_FILE) -> dict[str, Query]:
    return parse_queries(path.read_text(encoding="utf-8"))


def get(name: str) -> Query:
    try:
        return catalog()[name]
    except KeyError:
        raise KeyError(f"no query named {name!r} in {QUERIES_FILE.name}") from None
