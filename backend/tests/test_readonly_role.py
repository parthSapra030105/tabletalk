"""
Wall #2: the database role itself refuses writes, whatever SQL reaches it.

These tests connect as the read-only role and try to change things. Each must fail
inside Postgres. They need the database from scripts/setup_db.py and are skipped
without it.
"""

import os
from pathlib import Path

import psycopg
import pytest
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")
APP_URL = os.environ.get("DATABASE_URL")
READER_URL = os.environ.get("READONLY_DATABASE_URL")
pytestmark = pytest.mark.skipif(not (APP_URL and READER_URL), reason="run scripts/setup_db.py first")

SCHEMA = "ds_readonly_test"


@pytest.fixture(scope="module", autouse=True)
def dataset():
    """A tiny dataset schema, set up exactly like an ingested upload."""
    with psycopg.connect(APP_URL, autocommit=True) as conn:
        conn.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")
        conn.execute(f"CREATE SCHEMA {SCHEMA}")
        conn.execute(f"GRANT USAGE ON SCHEMA {SCHEMA} TO tabletalk_reader")
        conn.execute(f"CREATE TABLE {SCHEMA}.orders (id int, amount numeric)")
        conn.execute(f"INSERT INTO {SCHEMA}.orders VALUES (1, 100), (2, 250)")
        conn.execute(f"GRANT SELECT ON {SCHEMA}.orders TO tabletalk_reader")
        conn.execute("CREATE TABLE IF NOT EXISTS public.app_secret (note text)")
    yield
    with psycopg.connect(APP_URL, autocommit=True) as conn:
        conn.execute(f"DROP SCHEMA {SCHEMA} CASCADE")
        conn.execute("DROP TABLE public.app_secret")


def run_as_reader(statement):
    with psycopg.connect(READER_URL, autocommit=True) as conn:
        return conn.execute(statement).fetchall()


def snapshot():
    with psycopg.connect(APP_URL) as conn:
        return conn.execute(f"SELECT id, amount FROM {SCHEMA}.orders ORDER BY id").fetchall()


def test_reader_can_select():
    assert run_as_reader(f"SELECT sum(amount) FROM {SCHEMA}.orders") == [(350,)]


@pytest.mark.parametrize("statement", [
    f"DELETE FROM {SCHEMA}.orders",
    f"UPDATE {SCHEMA}.orders SET amount = 0",
    f"INSERT INTO {SCHEMA}.orders VALUES (3, 1)",
    f"TRUNCATE {SCHEMA}.orders",
    f"DROP TABLE {SCHEMA}.orders",
    f"ALTER TABLE {SCHEMA}.orders ADD COLUMN x int",
    f"CREATE TABLE {SCHEMA}.evil (x int)",
    "CREATE TEMP TABLE scratch (x int)",
    f"SELECT 1; DELETE FROM {SCHEMA}.orders",
])
def test_reader_cannot_write(statement):
    with pytest.raises(psycopg.Error):
        run_as_reader(statement)
    assert snapshot() == [(1, 100), (2, 250)]


def test_turning_off_read_only_still_cannot_write():
    """A session can switch read-only off for itself; table privileges are the second layer."""
    with psycopg.connect(READER_URL, autocommit=True) as conn:
        conn.execute("SET default_transaction_read_only = off")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(f"DELETE FROM {SCHEMA}.orders")
    assert snapshot() == [(1, 100), (2, 250)]


def test_reader_cannot_see_app_tables():
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        run_as_reader("SELECT * FROM public.app_secret")


def test_statement_timeout_stops_long_queries():
    with pytest.raises(psycopg.errors.QueryCanceled):
        run_as_reader("SELECT pg_sleep(12)")
