"""
Workbook -> clean, typed rows, one table at a time.

For each sheet:
    1. find its tables. A sheet small enough to hold in memory (anything made by hand)
       is split into tables by blocks.find_blocks: side by side, stacked, with titles and
       notes around them. A bigger sheet is an export: one table, streamed, with the
       header found in its first rows.
    2. clean column names (originals are kept for the catalog)
    3. infer each column's type from a sample of data rows
    4. stream every row: skip junk (blank, total/footer, exact duplicate) with a reason,
       coerce values, and hand chunks of rows to a sink

The sink decides where rows go (a Postgres COPY, or just a counter in a dry run).
Memory stays bounded by the reader, the sample, the chunk size and one hash per row;
only sheets under BLOCK_CELL_LIMIT are held whole.
"""

import logging
import re
import time
from dataclasses import dataclass, field
from itertools import chain, islice
from operator import itemgetter

from openpyxl.utils import get_column_letter

from .blocks import find_blocks
from .headers import HEADER_SCAN_ROWS, clean_name, find_header, unique_names
from .readers import WorkbookReader
from .values import ColumnType, infer_type, is_null

SAMPLE_ROWS = 20_000
CHUNK_ROWS = 50_000
MAX_EXAMPLES = 5
MAX_COLUMNS = 1600         # Postgres' hard limit on columns per table
BLOCK_CELL_LIMIT = 2_000_000   # sheets up to this many cells are read whole and split into tables

log = logging.getLogger(__name__)

_TOTAL_ROW = re.compile(r"^\s*(grand\s*|sub\s*)?totals?\b", re.IGNORECASE)
# Numbers that are labels, not quantities: summing or averaging them means nothing, and they can
# hold several codes in one cell ("411001 + 411002"). They are stored as text.
_IDENTIFIER = re.compile(r"(^|_)(pin|pins|pincodes?|pin_codes?|zip|zipcodes?|postcodes?|postal_codes?|phone|mobile)($|_)")


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
    """One table loaded from a sheet, or a sheet (or part of one) that was skipped."""
    sheet: str
    table: str | None = None
    status: str = "loaded"            # loaded | skipped
    reason: str | None = None         # why a sheet was skipped
    reader: str | None = None
    range: str | None = None          # the cells the table came from, e.g. "B3:P58"
    title: str | None = None          # text above the table on the sheet
    notes: list = field(default_factory=list)                 # notes typed around the table
    hidden: bool = False              # the sheet is hidden in Excel
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

    def abort_table(self, exc):
        """Undo the table that was being written when a sheet failed."""
        pass


@dataclass
class _Table:
    """A table ready to load: where its rows come from, before typing."""
    report: SheetReport
    name: str
    header: tuple
    rows: object                      # iterable of (excel_row, row tuple)
    width: int | None = None          # None: worked out from the header and a sample
    skipped: list = field(default_factory=list)              # (excel_row, reason) found while splitting


def ingest_workbook(path, sink=None, progress=None):
    """Load every table in the workbook. Returns a list of SheetReport, one per table or skipped part."""
    sink = sink or Sink()
    reader = WorkbookReader(path)
    reports, used_tables = [], set()
    try:
        for info in reader.sheets():
            try:
                tables, skipped = _sheet_tables(reader, info)
            except Exception as exc:
                log.exception("sheet %r couldn't be split into tables", info.name)
                tables, skipped = [], [SheetReport(sheet=info.name, reader=reader.reader_for(info), status="skipped",
                                                   reason=f"couldn't be loaded: {_first_line(exc)}")]
            for r in [t.report for t in tables] + skipped:
                r.hidden = info.hidden
            for t in tables:
                start = time.perf_counter()
                try:
                    _load_table(t, sink, used_tables, progress, info)
                except Exception as exc:
                    # One bad table is skipped and reported; the rest of the workbook still loads.
                    log.exception("table %r on sheet %r failed", t.name, info.name)
                    sink.abort_table(exc)
                    r = t.report
                    r.status, r.reason = "skipped", f"couldn't be loaded: {_first_line(exc)}"
                    r.table, r.rows_loaded, r.skipped_rows, r.columns = None, 0, {}, []
                t.report.seconds = round(time.perf_counter() - start, 2)
                reports.append(t.report)
            reports.extend(skipped)
    finally:
        reader.close()
    return reports


def _first_line(exc):
    text = str(exc).strip()
    return text.splitlines()[0][:200] if text else type(exc).__name__


def _sheet_tables(reader, info):
    """The tables on one sheet, and reports for anything on it that was skipped."""
    kind = reader.reader_for(info)
    base = clean_name(info.name, 0)
    if kind != "calamine" or info.cells is None or info.cells > BLOCK_CELL_LIMIT:
        rows = reader.rows(info)
        head = list(islice(rows, HEADER_SCAN_ROWS))
        h = find_header(head)
        if h is None:
            reason = "empty sheet" if not any(map(any, head)) else "no header row found"
            return [], [SheetReport(sheet=info.name, reader=kind, status="skipped", reason=reason)]
        report = SheetReport(sheet=info.name, reader=kind, header_row=h + 1)
        pairs = enumerate(chain(head[h + 1:], rows), start=h + 2)
        return [_Table(report, base, head[h], pairs)], []

    grid, first_col = reader.grid(info)
    blocks, leftovers = find_blocks(grid)
    if not blocks:
        reason = "empty sheet" if not any(map(any, grid)) else "no header row found"
        return [], [SheetReport(sheet=info.name, reader=kind, status="skipped", reason=reason)]

    def cells(top, bottom, left, right):
        return f"{get_column_letter(first_col + left + 1)}{top + 1}:{get_column_letter(first_col + right)}{bottom}"

    tables = []
    for k, b in enumerate(blocks):
        # Several tables on a sheet are named by a short title line ("Meta RnF"), not a "Key: value" line.
        label = next((t for t in b.title if len(t.split()) <= 8 and ": " not in t), None)
        if len(blocks) == 1:
            name = base
        elif label:
            name = clean_name(f"{info.name} {label}", 0)
        else:
            name = base if k == 0 else f"{base}_{k + 1}"
        report = SheetReport(sheet=info.name, reader=kind, header_row=b.header_row + 1,
                             range=cells(b.top, b.bottom, b.left, b.right),
                             title=" · ".join(dict.fromkeys(b.title)) or None, notes=b.notes)
        pick = itemgetter(*b.columns) if len(b.columns) > 1 else (lambda row, c=b.columns[0]: (row[c],))
        rows = [(i + 1, pick(grid[i])) for i in b.rows]
        tables.append(_Table(report, name, b.header, rows, width=len(b.columns),
                             skipped=[(i + 1, reason) for i, reason in sorted(b.skipped)]))

    skipped = []
    for r in leftovers:
        values = [grid[i][c] for i in range(r.top, r.bottom) for c in range(r.left, r.right) if grid[i][c] is not None]
        if r.bottom - r.top >= 2 and r.right - r.left >= 2 and len(values) >= 4:
            skipped.append(SheetReport(sheet=info.name, reader=kind, status="skipped", reason="no header row found",
                                       range=cells(r.top, r.bottom, r.left, r.right)))
        else:
            tables[0].report.notes.extend(str(v).strip()[:200] for v in values if isinstance(v, str))
    return tables, skipped


def _load_table(t, sink, used_tables, progress, info):
    report = t.report
    rows = iter(t.rows)
    # Sample the rows right after the header to infer types.
    sample = list(islice(rows, SAMPLE_ROWS))
    header = t.header
    width = t.width or max(_last_filled(header), *(_last_filled(r) for _, r in sample[:1000]), 0)
    if width > MAX_COLUMNS:
        report.status = "skipped"
        report.reason = f"too wide: {width:,} columns, but a table can have at most {MAX_COLUMNS:,}"
        return

    names = unique_names([clean_name(header[i] if i < len(header) else None, i) for i in range(width)])
    table = _unique_table_name(t.name, used_tables)
    report.table = table

    sample_rows = [_pad(r, width) for _, r in sample if any(v is not None for v in r) and not _is_total(r)]
    columns = []
    for i, name in enumerate(names):
        original = header[i] if i < len(header) else None
        values = [r[i] for r in sample_rows if not is_null(r[i])]
        kind = infer_type(values)
        if kind.sql_type == "numeric" and _IDENTIFIER.search(name):
            kind = ColumnType("text")
        columns.append(Column(name, None if original is None else str(original), kind))
    col_reports = [ColumnReport(c.name, c.original, c.type.sql_type) for c in columns]
    for c, cr in zip(columns, col_reports):
        if c.type.ambiguous_day_month:
            cr.note = "every date in the sample has day and month <= 12; read as DD/MM"

    sink.begin_table(table, columns)
    for excel_row, reason in t.skipped:
        _record_skip(report, reason, excel_row)
    seen = set()
    chunk = []
    for excel_row, raw in chain(sample, rows):
        row = _pad(raw, width)
        reason = _skip_reason(row, seen)
        if reason:
            _record_skip(report, reason, excel_row)
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


def _record_skip(report, reason, excel_row):
    entry = report.skipped_rows.setdefault(reason, {"count": 0, "examples": []})
    entry["count"] += 1
    if len(entry["examples"]) < MAX_EXAMPLES:
        entry["examples"].append(excel_row)


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
