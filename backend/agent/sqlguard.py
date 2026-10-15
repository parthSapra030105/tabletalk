"""
Wall #1: decide in code, before anything reaches the database, whether a model-written
query may run. Parse it, never pattern-match it.

A query passes only if:
    - it parses as exactly one statement, and that statement is a query (SELECT / UNION / ...)
    - nowhere in its tree is there a write, DDL, SET, COPY, lock, SELECT INTO or raw command.
      The whole tree is walked because "WITH d AS (DELETE ... RETURNING *) SELECT * FROM d"
      and "SELECT * INTO new_table ..." are both SELECTs at the top level
    - it calls no function that can sleep, read files, reach other databases or change settings
    - every table is a table of this dataset (no other schema, no system catalogs)
    - every column exists in the tables it reads (or is an alias defined in the query)
Then a LIMIT is added or tightened, so a result can never be larger than the row cap.

Wall #2, the read-only database role, still applies after this. Either wall alone would
stop the brief's attacks; both must fail for a write to happen.
"""

import logging
from dataclasses import dataclass

import sqlglot
from sqlglot import exp

logging.getLogger("sqlglot").setLevel(logging.ERROR)   # unparseable input is reported as a rejection, not a log line

MAX_SQL_CHARS = 5_000
ROW_CAP = 1_000

FORBIDDEN_NODES = tuple(getattr(exp, name) for name in [
    "Insert", "Update", "Delete", "Merge", "Create", "Drop", "Alter", "TruncateTable", "Command", "Set",
    "Into", "Lock", "Copy", "Grant", "Revoke", "Transaction", "Commit", "Rollback", "Use", "Pragma",
    "Analyze", "LoadData", "Kill",
] if hasattr(exp, name))

FORBIDDEN_FUNCTION_PREFIXES = ("pg_", "lo_", "dblink", "set_config", "current_setting", "nextval", "setval",
                               "currval", "query_to_xml", "table_to_xml", "cursor_to_xml", "database_to_xml",
                               "schema_to_xml", "txid_", "file_", "copy")


class QueryRejected(Exception):
    """The query may not run. The message is written so the SQL node can fix its query."""


@dataclass
class CheckedQuery:
    sql: str            # what will actually run (LIMIT applied)
    tables: list


def check(sql, catalog, row_cap=ROW_CAP):
    if not sql or not sql.strip():
        raise QueryRejected("The query is empty.")
    if len(sql) > MAX_SQL_CHARS:
        raise QueryRejected(f"The query is longer than {MAX_SQL_CHARS} characters.")
    try:
        statements = [s for s in sqlglot.parse(sql, read="postgres") if s is not None]
    except sqlglot.errors.ParseError as e:
        raise QueryRejected(f"The query could not be parsed: {str(e).splitlines()[0]}")
    if len(statements) != 1:
        raise QueryRejected(f"Exactly one statement is allowed; found {len(statements)}.")
    root = statements[0]
    if not isinstance(root, exp.Query):
        raise QueryRejected(f"Only SELECT queries are allowed; this is a {root.key.upper()} statement.")

    for node in root.walk():
        if isinstance(node, FORBIDDEN_NODES):
            raise QueryRejected(f"Only reading is allowed; the query contains {node.key.upper()}.")
        if isinstance(node, exp.Func):
            name = (node.name if isinstance(node, exp.Anonymous) else node.sql_name()).lower()
            if name.startswith(FORBIDDEN_FUNCTION_PREFIXES):
                raise QueryRejected(f"The function {name}() is not allowed.")

    tables = _check_tables(root, catalog)
    _check_columns(root, catalog, tables)
    _keep_empty_results_empty(root)
    _apply_limit(root, row_cap)
    return CheckedQuery(sql=root.sql(dialect="postgres", comments=False), tables=sorted(set(tables.values())))


def _cte_names(root):
    return {cte.alias_or_name.lower() for cte in root.find_all(exp.CTE)}


def _check_tables(root, catalog):
    """Returns {alias or name used in the query: real table name}."""
    known = {t["name"] for t in catalog["tables"]}
    ctes = _cte_names(root)
    used = {}
    for t in root.find_all(exp.Table):
        if not isinstance(t.this, exp.Identifier):     # a table function such as generate_series(...)
            continue
        name = t.name.lower()
        if t.args.get("catalog") or (t.db and t.db.lower() != catalog["schema"]):
            raise QueryRejected(f"Only tables of this dataset can be queried; '{t.sql()}' is outside it.")
        if name in ctes and not t.db:
            continue
        if name not in known:
            raise QueryRejected(f"Unknown table '{name}'. Available tables: {', '.join(sorted(known))}.")
        used[(t.alias or name).lower()] = name
    if not used and not ctes:
        raise QueryRejected("The query must read from at least one table of this dataset.")
    return used


def _check_columns(root, catalog, tables):
    columns_of = {t["name"]: {c["name"] for c in t["columns"]} for t in catalog["tables"]}
    # Names the query itself defines: output aliases, CTE and subquery names and their columns.
    defined = {a.alias.lower() for a in root.find_all(exp.Alias)}
    defined |= {a.alias_or_name.lower() for a in root.find_all(exp.CTE, exp.Subquery) if a.alias_or_name}
    for ta in root.find_all(exp.TableAlias):
        defined |= {c.name.lower() for c in ta.columns}
    readable = set().union(*(columns_of[t] for t in tables.values())) if tables else set()

    for col in root.find_all(exp.Column):
        if isinstance(col.this, exp.Star):
            continue
        name, qualifier = col.name.lower(), col.table.lower()
        if qualifier in tables:
            if name not in columns_of[tables[qualifier]]:
                raise QueryRejected(f"Unknown column '{qualifier}.{name}'. Columns of {tables[qualifier]}: "
                                    f"{', '.join(sorted(columns_of[tables[qualifier]]))}.")
        elif qualifier:
            continue                                     # a CTE or subquery alias; its columns come from the query
        elif name not in readable and name not in defined:
            raise QueryRejected(f"Unknown column '{name}' in the tables this query reads "
                                f"({', '.join(sorted(set(tables.values())))}).")


def _keep_empty_results_empty(root):
    """COALESCE(SUM(x), 0) turns 'no rows matched' into a confident zero, so a question about a
    year with no data would come back as '₹0'. Unwrap it: an empty result stays NULL and is
    reported as no data."""
    for node in list(root.find_all(exp.Coalesce)):
        fallbacks = node.expressions
        if (isinstance(node.this, exp.AggFunc) and fallbacks
                and all(isinstance(f, exp.Literal) and f.is_number for f in fallbacks)):
            node.replace(node.this)


def _apply_limit(root, row_cap):
    """Add a LIMIT, or replace one that isn't a literal or reaches the cap. One row over the cap
    is fetched so the caller can tell the result was truncated."""
    limit = root.args.get("limit")
    current = None
    if limit is not None and isinstance(limit.expression, exp.Literal) and limit.expression.is_int:
        current = int(limit.expression.name)
    if current is None or current >= row_cap:
        root.limit(row_cap + 1, copy=False)
