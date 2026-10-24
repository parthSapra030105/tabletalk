"""
Load a workbook into Postgres.

One schema per upload (ds_1, ds_2, ...), one table per sheet, rows streamed in
with COPY. The whole workbook loads inside one transaction, so a half-loaded
dataset can never be queried. Each table gets its own savepoint inside it: a
sheet that fails is rolled back and reported as skipped, and the others still load.

The read-only role gets USAGE on the schema and SELECT on each table, nothing more.
"""

import os

import psycopg
from psycopg import sql

from catalog.profile import build_catalog

from .pipeline import Sink, ingest_workbook

READER_ROLE = "tabletalk_reader"


class NoUsableSheet(Exception):
    """No sheet in the workbook had a header row and data."""


class PostgresSink(Sink):
    def __init__(self, conn, schema):
        self.conn = conn
        self.schema = schema
        self._cur = conn.cursor()
        self._savepoint = None
        self._copy_ctx = None
        self._copy = None

    def begin_table(self, table, columns):
        self._table = sql.Identifier(self.schema, table)
        self._savepoint = self.conn.transaction()
        self._savepoint.__enter__()
        # sql_type comes from a fixed set in values.ColumnType, never from the file.
        cols = sql.SQL(", ").join(sql.SQL("{} {}").format(sql.Identifier(c.name), sql.SQL(c.type.sql_type))
                                  for c in columns)
        self._cur.execute(sql.SQL("CREATE TABLE {} ({})").format(self._table, cols))
        self._copy_ctx = self._cur.copy(sql.SQL("COPY {} FROM STDIN").format(self._table))
        self._copy = self._copy_ctx.__enter__()

    def write(self, rows):
        for row in rows:
            self._copy.write_row(row)

    def end_table(self):
        self._copy_ctx.__exit__(None, None, None)
        self._copy_ctx = self._copy = None
        self._cur.execute(sql.SQL("ANALYZE {}").format(self._table))
        self._cur.execute(sql.SQL("GRANT SELECT ON {} TO {}").format(self._table, sql.Identifier(READER_ROLE)))
        self._savepoint.__exit__(None, None, None)
        self._savepoint = None

    def abort_table(self, exc):
        """End an in-flight COPY, then roll back to this table's savepoint."""
        if self._copy_ctx is not None:
            try:
                self._copy_ctx.__exit__(type(exc), exc, exc.__traceback__)
            except Exception:
                pass
            self._copy_ctx = self._copy = None
        if self._savepoint is not None:
            self._savepoint.__exit__(type(exc), exc, exc.__traceback__)
            self._savepoint = None

    def abort(self, exc):
        """Clean up so the whole workbook's transaction can roll back."""
        self.abort_table(exc)


def next_schema_name(conn):
    row = conn.execute(
        r"SELECT max(substring(nspname from 4)::int) FROM pg_namespace WHERE nspname ~ '^ds_\d+$'").fetchone()
    return f"ds_{(row[0] or 0) + 1}"


def load_workbook(path, dsn=None, schema=None, progress=None):
    """Ingest a workbook into a new schema and build its catalog. Returns (schema, sheet reports, catalog)."""
    dsn = dsn or os.environ["DATABASE_URL"]
    with psycopg.connect(dsn) as conn:
        schema = schema or next_schema_name(conn)
        sink = PostgresSink(conn, schema)
        with conn.transaction():
            try:
                conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
                conn.execute(sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(sql.Identifier(schema),
                                                                              sql.Identifier(READER_ROLE)))
                reports = ingest_workbook(path, sink, progress)
                if not any(r.status == "loaded" for r in reports):
                    raise NoUsableSheet("; ".join(f"{r.sheet}: {r.reason}" for r in reports) or "no sheets")
            except BaseException as exc:
                sink.abort(exc)
                raise
            # Same transaction: a dataset is never visible without its catalog and indexes.
            catalog = build_catalog(conn, schema, reports)
    return schema, reports, catalog
