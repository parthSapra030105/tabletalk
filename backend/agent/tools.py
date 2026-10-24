"""
The three tools from the brief. All database access goes through here.

    list_tables(catalog)            tables and row counts, from the catalog (no database call)
    describe_table(catalog, name)   columns, types, descriptions and sample values (no database call)
    run_query(sql, catalog)         validated, read-only, row-capped, time-limited

The safety lives inside run_query itself, so it holds whoever calls the tool:
a graph node today, an MCP client later.
"""

import os
import time
from dataclasses import dataclass, field

import psycopg
from psycopg import sql as pgsql

from .sqlguard import ROW_CAP, QueryRejected, check

STATEMENT_TIMEOUT = "10s"
# Real questions on the 1M-row sample plan at 15k-23k; a keyless self-join plans at ~286M and a
# cross join at ~1.1B. 5M leaves ~200x headroom for legitimate queries.
MAX_PLAN_COST = 5_000_000


@dataclass
class QueryResult:
    sql: str                       # exactly what ran
    columns: list
    rows: list                     # at most ROW_CAP rows
    truncated: bool                # True if the query had more rows than ROW_CAP
    seconds: float
    tables: list = field(default_factory=list)


def list_tables(catalog):
    return [{"name": t["name"], "sheet": t.get("sheet", ""), "hidden": t.get("hidden", False), "rows": t["row_count"],
             "description": t.get("description", "")}
            for t in catalog["tables"]]


def describe_table(catalog, name):
    table = next((t for t in catalog["tables"] if t["name"] == name), None)
    if table is None:
        raise KeyError(f"Unknown table '{name}'")
    return {
        "name": table["name"],
        "rows": table["row_count"],
        "description": table.get("description", ""),
        "columns": [{k: c[k] for k in ("name", "original", "type", "description", "null_pct", "min", "max")
                     if k in c} | {"values": [v for v, _ in c.get("top_values", [])][:20] or c.get("samples", [])}
                    for c in table["columns"]],
    }


def run_query(sql, catalog, dsn=None, row_cap=ROW_CAP, max_plan_cost=MAX_PLAN_COST):
    """Raises QueryRejected (wall #1 or the cost check) or psycopg.Error (the database refused or failed)."""
    checked = check(sql, catalog, row_cap)
    dsn = dsn or os.environ["READONLY_DATABASE_URL"]
    start = time.perf_counter()
    with psycopg.connect(dsn) as conn:
        conn.read_only = True                             # the transaction itself is READ ONLY, on top of the role
        with conn.transaction():
            conn.execute(pgsql.SQL("SET LOCAL search_path TO {}").format(pgsql.Identifier(catalog["schema"])))
            conn.execute(pgsql.SQL("SET LOCAL statement_timeout = {}").format(pgsql.Literal(STATEMENT_TIMEOUT)))
            plan = conn.execute("EXPLAIN (FORMAT JSON) " + checked.sql).fetchone()[0][0]["Plan"]
            if plan["Total Cost"] > max_plan_cost:
                raise QueryRejected(
                    f"The query is too expensive to run (planner cost {plan['Total Cost']:,.0f}). "
                    "This usually means a join without a matching key; join on the key columns listed in the catalog.")
            cur = conn.execute(checked.sql)
            columns = [d.name for d in cur.description]
            rows = cur.fetchmany(row_cap + 1)
    return QueryResult(sql=checked.sql, columns=columns, rows=rows[:row_cap], truncated=len(rows) > row_cap,
                       seconds=round(time.perf_counter() - start, 3), tables=checked.tables)
