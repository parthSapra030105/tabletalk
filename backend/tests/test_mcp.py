"""
The MCP server, driven the way a real client drives it: started as a subprocess and spoken to
over stdio. Needs a ready dataset (python manage.py load_sample); skipped without one.
"""

import asyncio
import json
import os
import sys
from pathlib import Path

import pytest
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")
BACKEND = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="run scripts/setup_db.py first")

ATTACKS = [
    "DELETE FROM orders WHERE status = 'Cancelled'",
    "SELECT * FROM orders; UPDATE orders SET net_amount = 0",
    "DROP TABLE orders",
    "WITH d AS (DELETE FROM orders RETURNING *) SELECT count(*) FROM d",
    "SELECT pg_sleep(30)",
    "SELECT * FROM public.api_dataset",
]


async def session_run(work):
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    params = StdioServerParameters(command=sys.executable, args=["mcp_server.py"], cwd=str(BACKEND), env=dict(os.environ))
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return await work(session)


def payload(result):
    if result.structured_content is not None:
        content = result.structured_content
        return content.get("result", content)
    return json.loads(result.content[0].text)


def call(name, **arguments):
    return asyncio.run(session_run(lambda s: s.call_tool(name, arguments)))


@pytest.fixture(scope="module")
def dataset_id():
    datasets = payload(call("list_datasets"))
    if not datasets:
        pytest.skip("no ready dataset; run python manage.py load_sample")
    return max(datasets, key=lambda d: d["rows"])["id"]      # the sample workbook, not small test uploads


def test_tools_are_listed_and_marked_read_only():
    tools = asyncio.run(session_run(lambda s: s.list_tools())).tools
    assert {t.name for t in tools} == {"list_datasets", "list_tables", "describe_table", "run_query"}
    assert all(t.annotations and t.annotations.read_only_hint for t in tools)


def test_describe_and_query(dataset_id):
    tables = {t["name"] for t in payload(call("list_tables", dataset_id=dataset_id))}
    assert "orders" in tables
    columns = {c["name"] for c in payload(call("describe_table", dataset_id=dataset_id, table="orders"))["columns"]}
    assert "region" in columns
    out = payload(call("run_query", dataset_id=dataset_id, sql="SELECT region, count(*) AS n FROM orders GROUP BY region ORDER BY region"))
    assert out["columns"] == ["region", "n"] and len(out["rows"]) == 4


def test_results_are_capped(dataset_id):
    out = payload(call("run_query", dataset_id=dataset_id, sql="SELECT * FROM orders"))
    assert len(out["rows"]) == 200 and out["truncated"]


@pytest.mark.parametrize("sql", ATTACKS)
def test_attacks_through_mcp_are_rejected(dataset_id, sql):
    before = payload(call("run_query", dataset_id=dataset_id, sql="SELECT count(*), sum(net_amount) FROM orders"))["rows"]
    result = call("run_query", dataset_id=dataset_id, sql=sql)
    assert result.is_error
    after = payload(call("run_query", dataset_id=dataset_id, sql="SELECT count(*), sum(net_amount) FROM orders"))["rows"]
    assert before == after
