"""Shared fixture: a freshly built and loaded schema in the configured database."""

import os

import oracledb
import pytest

from social_analytics.db import connect
from social_analytics.etl.load import load
from social_analytics.sql_runner import run_script, schema_scripts


@pytest.fixture(scope="session")
def conn():
    try:
        connection = connect()
    except (oracledb.Error, RuntimeError) as error:
        if os.getenv("CI"):
            pytest.fail(f"Oracle is required in CI but not reachable: {error}")
        pytest.skip(f"Oracle not reachable ({error}); start it with `docker compose up -d`")

    with connection:
        for path in schema_scripts():
            run_script(connection, path)
        load(connection)
        yield connection
