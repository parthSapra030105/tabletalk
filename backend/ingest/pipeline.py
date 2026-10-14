"""
Workbook -> clean, typed rows, one sheet at a time.

For each sheet:
    1. find the header row (title and spacer rows above it are ignored)
    2. clean column names (originals are kept for the catalog)
    3. infer each column's type from a sample of data rows
    4. stream every row: skip junk (blank, total/footer, exact duplicate) with a reason,
       coerce values, and hand chunks of rows to a sink

The sink decides where rows go (a Postgres COPY, or just a counter in a dry run).
Memory stays bounded by the reader, the sample, the chunk size and one hash per row.
"""

import re
import time
from dataclasses import dataclass, field
from itertools import chain, islice

from .headers import HEADER_SCAN_ROWS, clean_name, find_header, unique_names
from .readers import WorkbookReader
from .values import ColumnType, infer_type, is_null

SAMPLE_ROWS = 20_000
CHUNK_ROWS = 50_000
MAX_EXAMPLES = 5

_TOTAL_ROW = re.compile(r"^\s*(grand\s*|sub\s*)?totals?\b", re.IGNORECASE)


@dataclass
class Column:
    name: str
    original: str | None
    type: ColumnType


@dataclass
class ColumnReport:
    name: str
    original: str | None
    type: str
    nulls: int = 0
    coercion_failures: int = 0
    failure_examples: list = field(default_factory=list)      # [(excel_row, raw value)]
    note: str | None = None


@dataclass
class SheetReport:
    sheet: str
    table: str | None = None
    status: str = "loaded"            # loaded | skipped
    reason: str | None = None         # why a sheet was skipped
    reader: str | None = None
    header_row: int | None = None     # 1-based, as Excel shows it
    rows_loaded: int = 0
    skipped_rows: dict = field(default_factory=dict)          # reason -> {"count", "examples": [excel rows]}
    columns: list = field(default_factory=list)
    seconds: float = 0.0


class Sink:
    """Where clean rows go. The Postgres loader implements the same three methods."""

    def begin_table(self, table, columns):
        pass

    def write(self, rows):
        pass

    def end_table(self):
        pass


def ingest_workbook(path, sink=None, progress=None):
    """Load every sheet in the workbook. Returns a list of SheetReport."""
    sink = sink or Sink()
    reader = WorkbookReader(path)
    reports, used_tables = [], set()
    try:
        for info in reader.sheets():
            report = SheetReport(sheet=info.name, reader=reader.reader_for(info))
            start = time.perf_counter()
            _ingest_sheet(reader, info, report, sink, used_tables, progress)
            report.seconds = round(time.perf_counter() - start, 2)
            reports.append(report)
    finally:
        reader.close()
    return reports


def _ingest_sheet(reader, info, report, sink, used_tables, progress):
    rows = reader.rows(info)
    head = list(islice(rows, HEADER_SCAN_ROWS))
    h = find_header(head)
    if h is None:
        report.status, report.reason = "skipped", "empty sheet" if not any(map(any, head)) else "no header row found"
        return
    report.header_row = h + 1

    # Sample the rows right after the header to infer types.
    body = chain(head[h + 1:], rows)
    sample = list(islice(body, SAMPLE_ROWS))
    header = head[h]
    width = max(_last_filled(header), *(_last_filled(r) for r in sample[:1000]), 0)

    names = unique_names([clean_name(header[i] if i < len(header) else None, i) for i in range(width)])
    table = _unique_table_name(clean_name(info.name, 0), used_tables)
    report.table = table

    sample_rows = [_pad(r, width) for r in sample if any(v is not None for v in r) and not _is_total(r)]
    columns = []
    for i, name in enumerate(names):
        original = header[i] if i < len(header) else None
        values = [r[i] for r in sample_rows if not is_null(r[i])]
        columns.append(Column(name, None if original is None else str(original), infer_type(values)))
    col_reports = [ColumnReport(c.name, c.original, c.type.sql_type) for c in columns]
    for c, cr in zip(columns, col_reports):
        if c.type.ambiguous_day_month:
            cr.note = "every date in the sample has day and month <= 12; read as DD/MM"

    sink.begin_table(table, columns)
    seen = set()
    chunk = []
    first_data_row = h + 2                     # Excel row number of the first row after the header
    for excel_row, raw in enumerate(chain(sample, body), start=first_data_row):
        row = _pad(raw, width)
        reason = _skip_reason(row, seen)
        if reason:
            entry = report.skipped_rows.setdefault(reason, {"count": 0, "examples": []})
            entry["count"] += 1
            if len(entry["examples"]) < MAX_EXAMPLES:
                entry["examples"].append(excel_row)
            continue
        out = []
        for i, v in enumerate(row):
            value, failed = columns[i].type.coerce(v)
            if value is None:
                col_reports[i].nulls += 1
            if failed:
                col_reports[i].coercion_failures += 1
                if len(col_reports[i].failure_examples) < MAX_EXAMPLES:
                    col_reports[i].failure_examples.append((excel_row, v))
            out.append(value)
        chunk.append(tuple(out))
        if len(chunk) >= CHUNK_ROWS:
            sink.write(chunk)
            report.rows_loaded += len(chunk)
            chunk = []
            if progress:
                progress(info.name, report.rows_loaded, info.rows)
    if chunk:
        sink.write(chunk)
        report.rows_loaded += len(chunk)
    sink.end_table()

    for c, cr in zip(columns, col_reports):
        if c.type.categories:
            cr.note = f"{len(set(c.type.categories.values()))} categories; case and spacing variants merged"
    report.columns = col_reports


def _skip_reason(row, seen):
    if all(v is None for v in row):
        return "blank row"
    if _is_total(row):
        return "total / summary row"
    key = hash(row)
    if key in seen:
        return "exact duplicate of an earlier row"
    seen.add(key)
    return None


def _is_total(row):
    return any(isinstance(v, str) and _TOTAL_ROW.match(v) for v in row[:2])


def _last_filled(row):
    for i in range(len(row) - 1, -1, -1):
        if row[i] is not None:
            return i + 1
    return 0


def _pad(row, width):
    if len(row) == width:
        return row
    return row[:width] if len(row) > width else row + (None,) * (width - len(row))


def _unique_table_name(name, used):
    candidate, n = name, 1
    while candidate in used:
        n += 1
        candidate = f"{name}_{n}"
    used.add(candidate)
    return candidate
