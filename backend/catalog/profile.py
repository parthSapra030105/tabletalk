"""
Build the catalog for one loaded dataset: what the model is told about the data.

Everything here is computed once, right after ingest, with plain SQL (no LLM):
    - per column: type, nulls, distinct count, min/max, top values (low cardinality)
      or a few samples (high cardinality), whether numbers are all whole
    - key candidates: unique, non-null columns
    - joins: a column whose values (almost) all appear in another table's key column
    - indexes on keys, join columns and dates, so the queries the model writes stay fast

Values that reach the catalog are trimmed to a short length: they will later be
shown to the model as data, and a long cell has no business in a prompt.
"""

import datetime as dt
import decimal
import re
import time

from psycopg import sql

TOP_VALUES_MAX_DISTINCT = 50     # columns with at most this many distinct values list them all
SAMPLE_COUNT = 5
VALUE_MAX_CHARS = 60
JOIN_SAMPLE = 200                # distinct values from a candidate column checked against a key
JOIN_MIN_OVERLAP = 0.95
KEY_MIN_DISTINCT = 10
NUMERIC_JOIN_MIN_DISTINCT = 50
PARALLEL_MIN_SHARED = 0.5        # tables sharing this share of their column names are parallel, not related
_ID_HINT = re.compile(r"(^|_)(id|code|no|num|key|ref|sku)($|_)|id$")
_PERCENT_HINT = re.compile(r"(^|_)(pct|percent|percentage|ctr|vtr|cvr|share|rate)($|_)")


def build_catalog(conn, schema, reports):
    """`reports` are the ingest SheetReports; they supply sheet names, original headers and ingest notes."""
    timings = {}
    start = time.perf_counter()
    tables = [_profile_table(conn, schema, r) for r in reports if r.status == "loaded"]
    timings["profile"] = time.perf_counter() - start

    start = time.perf_counter()
    keys = [(t, c) for t in tables for c in t["columns"] if c["is_key"]]
    for t, c in keys:
        _index(conn, schema, t["name"], c["name"])
    joins = _find_joins(conn, schema, tables, keys)
    for j in joins:
        _index(conn, schema, j["from_table"], j["from_column"])
    for t in tables:
        for c in t["columns"]:
            if c["type"] in ("date", "timestamp"):
                _index(conn, schema, t["name"], c["name"])
        conn.execute(sql.SQL("ANALYZE {}").format(sql.Identifier(schema, t["name"])))
    timings["keys, joins, indexes"] = time.perf_counter() - start

    return {
        "schema": schema,
        "tables": tables,
        "joins": joins,
        "timings": {k: round(v, 2) for k, v in timings.items()},
    }


def _profile_table(conn, schema, report):
    table = sql.Identifier(schema, report.table)
    cols = report.columns
    aggregates = [sql.SQL("count(*)")]
    for c in cols:
        ident = sql.Identifier(c.name)
        aggregates += [sql.SQL("count({})").format(ident), sql.SQL("count(DISTINCT {})").format(ident)]
        if c.type in ("numeric", "date", "timestamp"):
            aggregates += [sql.SQL("min({})").format(ident), sql.SQL("max({})").format(ident)]
        if c.type == "numeric":
            aggregates.append(sql.SQL("bool_and({0} = trunc({0}))").format(ident))
    row = conn.execute(sql.SQL("SELECT {} FROM {}").format(sql.SQL(", ").join(aggregates), table)).fetchone()

    values = iter(row)
    row_count = next(values)
    columns = []
    for c in cols:
        non_null, distinct = next(values), next(values)
        col = {
            "name": c.name,
            "original": c.original,
            "type": c.type,
            "null_pct": round(100 * (row_count - non_null) / row_count, 1) if row_count else 0.0,
            "distinct": distinct,
        }
        if c.type in ("numeric", "date", "timestamp"):
            col["min"], col["max"] = _plain(next(values)), _plain(next(values))
        if c.type == "numeric":
            col["whole_numbers"] = bool(next(values))
            if _is_fraction(c, col):
                col["fraction"] = True
        col["is_key"] = (non_null == row_count and distinct == row_count and distinct >= KEY_MIN_DISTINCT
                         and c.type in ("text", "numeric") and col.get("whole_numbers", True))
        if 0 < distinct <= TOP_VALUES_MAX_DISTINCT:
            col["top_values"] = _top_values(conn, table, c.name)
        elif distinct:
            col["samples"] = _samples(conn, table, c.name)
        if c.note:
            col["ingest_note"] = c.note
        columns.append(col)

    table_entry = {"name": report.table, "sheet": report.sheet, "row_count": row_count,
                   "skipped_rows": {k: v["count"] for k, v in report.skipped_rows.items()}, "columns": columns}
    # Where the table sits in the workbook. Titles and notes are cell text: data, like any value.
    for key in ("range", "title", "notes", "hidden"):
        if getattr(report, key, None):
            table_entry[key] = [_plain(n) for n in report.notes] if key == "notes" else _plain(getattr(report, key))
    return table_entry


def _is_fraction(report_column, col):
    """A percentage stored as a share of 1 (0.25 for 25%), as Excel does under a % format."""
    named = "%" in (report_column.original or "") or _PERCENT_HINT.search(col["name"])
    return bool(named) and col["min"] is not None and 0 <= col["min"] and col["max"] <= 1


def _top_values(conn, table, column):
    ident = sql.Identifier(column)
    rows = conn.execute(sql.SQL("SELECT {0}, count(*) FROM {1} WHERE {0} IS NOT NULL GROUP BY {0} ORDER BY 2 DESC")
                        .format(ident, table)).fetchall()
    return [[_plain(v), n] for v, n in rows]


def _samples(conn, table, column):
    ident = sql.Identifier(column)
    rows = conn.execute(sql.SQL("SELECT DISTINCT {0} FROM (SELECT {0} FROM {1} WHERE {0} IS NOT NULL LIMIT 1000) s LIMIT %s")
                        .format(ident, table), (SAMPLE_COUNT,)).fetchall()
    return [_plain(v) for (v,) in rows]


def _find_joins(conn, schema, tables, keys):
    """
    A join is column A -> key column B (in another table) when nearly all of A's values exist in B.
    Names are ignored for text columns (they differ across sheets on purpose: cust_id vs customerid).
    Numeric columns also need an id-like name, otherwise counts such as qty = 1..10 would "match" a numeric id.
    Tables sharing most of their columns are parallel (versions of one plan, one per platform), not
    related: their city or pincode columns overlap, but joining them would mix two plans together.
    """
    joins = []
    names = {t["name"]: {c["name"] for c in t["columns"]} for t in tables}

    def parallel(a, b):
        # At least two shared columns: a small lookup table shares just its key with the table using it.
        shared = len(names[a["name"]] & names[b["name"]])
        return shared >= 2 and shared >= PARALLEL_MIN_SHARED * min(len(names[a["name"]]), len(names[b["name"]]))

    for t in tables:
        for c in t["columns"]:
            if c["type"] not in ("text", "numeric") or c["distinct"] < 2:
                continue
            if c["type"] == "numeric" and (c["distinct"] < NUMERIC_JOIN_MIN_DISTINCT or not _ID_HINT.search(c["name"])
                                           or not c.get("whole_numbers")):
                continue
            sample = None
            for kt, kc in keys:
                if kt is t or kc["type"] != c["type"] or c["distinct"] > kc["distinct"] or parallel(t, kt):
                    continue
                if sample is None:
                    sample = [v for (v,) in conn.execute(
                        sql.SQL("SELECT DISTINCT {0} FROM {1} WHERE {0} IS NOT NULL LIMIT %s")
                        .format(sql.Identifier(c["name"]), sql.Identifier(schema, t["name"])), (JOIN_SAMPLE,))]
                found = conn.execute(sql.SQL("SELECT count(*) FROM {} WHERE {} = ANY(%s)")
                                     .format(sql.Identifier(schema, kt["name"]), sql.Identifier(kc["name"])),
                                     (sample,)).fetchone()[0]
                overlap = found / len(sample)
                if overlap >= JOIN_MIN_OVERLAP:
                    joins.append({"from_table": t["name"], "from_column": c["name"],
                                  "to_table": kt["name"], "to_column": kc["name"],
                                  "overlap": round(overlap, 3), "one_to_one": c["is_key"]})
    return joins


def _index(conn, schema, table, column):
    name = f"ix_{table}_{column}"[:63]
    conn.execute(sql.SQL("CREATE INDEX IF NOT EXISTS {} ON {} ({})").format(
        sql.Identifier(name), sql.Identifier(schema, table), sql.Identifier(column)))


def _plain(v):
    """Make a value JSON-friendly and short."""
    if isinstance(v, decimal.Decimal):
        return int(v) if v == v.to_integral_value() else float(v)
    if isinstance(v, (dt.date, dt.datetime)):
        return v.isoformat()
    if isinstance(v, str) and len(v) > VALUE_MAX_CHARS:
        return v[:VALUE_MAX_CHARS] + "…"
    return v
