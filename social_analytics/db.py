"""Oracle connection and query helpers built on python-oracledb.

python-oracledb runs in "thin" mode by default: pure Python, no Oracle
Instant Client required, and supported for Oracle Database 12.1 and later.
Thick mode is enabled only when ORACLE_CLIENT_LIB_DIR is set.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import oracledb

from .config import Settings

if TYPE_CHECKING:
    import pandas as pd

Params = dict[str, Any] | None


def connect(settings: Settings | None = None) -> oracledb.Connection:
    """Open a connection; use it as a context manager to close it reliably."""
    settings = settings or Settings.from_env()
    if settings.client_lib_dir and oracledb.is_thin_mode():
        oracledb.init_oracle_client(lib_dir=settings.client_lib_dir)
    return oracledb.connect(user=settings.user, password=settings.password, dsn=settings.dsn)


def fetch(conn: oracledb.Connection, sql: str, params: Params = None):
    """Run a query and return (lowercase column names, rows)."""
    with conn.cursor() as cursor:
        cursor.execute(sql, params or {})
        columns = [description[0].lower() for description in cursor.description]
        return columns, cursor.fetchall()


def fetch_df(conn: oracledb.Connection, sql: str, params: Params = None) -> pd.DataFrame:
    """Run a query and return the result as a pandas DataFrame."""
    import pandas as pd

    columns, rows = fetch(conn, sql, params)
    return pd.DataFrame(rows, columns=columns)
