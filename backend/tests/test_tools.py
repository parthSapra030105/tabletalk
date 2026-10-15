"""
The tools against a real database: correct answers, row caps, the cost check, and the
brief's attacks sent straight to run_query. Needs scripts/setup_db.py; skipped without it.
"""

import os
from pathlib import Path

import psycopg
import pytest
from dotenv import load_dotenv

from agent.sqlguard import QueryRejected
from agent.tools import describe_table, list_tables, run_query

load_dotenv(Path(__file__).resolve().parents[2] / ".env")
APP_URL = os.environ.get("DATABASE_URL")
pytestmark = pytest.mark.skipif(not (APP_URL and os.environ.get("READONLY_DATABASE_URL")),
                                reason="run scripts/setup_db.py first")

SCHEMA = "ds_tools_test"
CATALOG = {
    "schema": SCHEMA,
    "tables": [
        {"name": "orders", "row_count": 200, "description": "One row per order.",
         "columns": [{"name": "order_id", "original": "Order ID", "type": "numeric", "null_pct": 0.0},
                     {"name": "region", "original": "Region", "type": "text", "null_pct": 0.0,
                      "top_values": [["North", 100], ["South", 100]]},
                     {"name": "amount", "original": "Amount", "type": "numeric", "null_pct": 0.0, "min": 1, "max": 200}]},
        {"name": "customers", "row_count": 50, "columns": [{"name": "customer_id", "original": "ID", "type": "numeric",
                                                             "null_pct": 0.0}]},
    ],
}


@pytest.fixture(scope="module", autouse=True)
def dataset():
    with psycopg.connect(APP_URL, autocommit=True) as conn:
        conn.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")
        conn.execute(f"CREATE SCHEMA {SCHEMA}")
        conn.execute(f"GRANT USAGE ON SCHEMA {SCHEMA} TO tabletalk_reader")
        conn.execute(f"CREATE TABLE {SCHEMA}.orders AS SELECT g AS order_id, "
                     f"CASE WHEN g % 2 = 0 THEN 'North' ELSE 'South' END AS region, g::numeric AS amount "
                     f"FROM generate_series(1, 200) g")
        conn.execute(f"CREATE TABLE {SCHEMA}.customers AS SELECT g AS customer_id FROM generate_series(1, 50) g")
        conn.execute(f"GRANT SELECT ON ALL TABLES IN SCHEMA {SCHEMA} TO tabletalk_reader")
    yield
    with psycopg.connect(APP_URL, autocommit=True) as conn:
        conn.execute(f"DROP SCHEMA {SCHEMA} CASCADE")


def fingerprint():
    with psycopg.connect(APP_URL) as conn:
        return conn.execute(f"SELECT md5(string_agg(o::text, ',' ORDER BY order_id)) FROM {SCHEMA}.orders o").fetchone()[0]


def test_list_and_describe_come_from_the_catalog():
    assert list_tables(CATALOG)[0] == {"name": "orders", "rows": 200, "description": "One row per order."}
    region = describe_table(CATALOG, "orders")["columns"][1]
    assert region["values"] == ["North", "South"]


def test_run_query_answers():
    r = run_query("SELECT region, SUM(amount) AS total FROM orders GROUP BY region ORDER BY region", CATALOG)
    assert r.columns == ["region", "total"]
    assert [(region, int(total)) for region, total in r.rows] == [("North", 10100), ("South", 10000)]
    assert not r.truncated and r.tables == ["orders"]


def test_big_results_are_capped_and_flagged():
    r = run_query("SELECT * FROM orders", CATALOG, row_cap=50)
    assert len(r.rows) == 50 and r.truncated


def test_runaway_join_is_refused_by_the_cost_check():
    with pytest.raises(QueryRejected, match="too expensive"):
        run_query("SELECT COUNT(*) FROM orders a, orders b, customers c", CATALOG, max_plan_cost=1_000)


# The brief's attacks, sent straight to the tool (the router would normally stop them earlier).
@pytest.mark.parametrize("sql", [
    "DELETE FROM orders WHERE region = 'North'",
    "DROP TABLE orders",
    "SELECT * FROM orders; UPDATE orders SET amount = 0",
    "WITH d AS (DELETE FROM orders RETURNING *) SELECT COUNT(*) FROM d",
    "SELECT pg_sleep(30)",
    "SELECT * FROM public.app_secret",
])
def test_attacks_change_nothing(sql):
    before = fingerprint()
    with pytest.raises((QueryRejected, psycopg.Error)):
        run_query(sql, CATALOG)
    assert fingerprint() == before
