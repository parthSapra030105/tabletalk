"""
Read rows from an .xlsx sheet, choosing the reader by sheet size.

- python-calamine: fast (Rust), but loads the whole sheet into memory first.
- openpyxl read-only: streams row by row with flat memory, but is several times slower.

The size check uses the sheet's <dimension> metadata via openpyxl, which costs
almost nothing. Sheets under CELL_BUDGET go to calamine; bigger ones, or ones with
no dimension recorded, are streamed. Both readers yield rows in one shape:
a tuple of Python values, with empty and whitespace-only cells as None and
midnight datetimes as dates.

Merged cells that span rows (a "Furniture" label covering five rows) have their
value repeated down every row they cover, so each row stands on its own. Merges
across columns are left alone: those are titles, and repeating a title across a
row would make it look like a header. Merges come from calamine, so only sheets
read with calamine get this; huge exports streamed with openpyxl rarely use merges.
"""

import datetime as dt
from dataclasses import dataclass

import openpyxl
from python_calamine import CalamineWorkbook

# ~15M cells is about 1.3 GB in calamine. Above that, stream with openpyxl.
CELL_BUDGET = 15_000_000


@dataclass
class SheetInfo:
    name: str
    rows: int | None      # from the file's metadata; None if the file doesn't record it
    cols: int | None
    hidden: bool = False  # hidden in Excel: often an older version or a working copy

    @property
    def cells(self):
        return None if self.rows is None or self.cols is None else self.rows * self.cols


class WorkbookReader:
    def __init__(self, path, cell_budget=CELL_BUDGET):
        self.path = path
        self.cell_budget = cell_budget
        self._openpyxl = openpyxl.load_workbook(path, read_only=True, data_only=True)
        self._calamine = None

    def sheets(self):
        return [SheetInfo(ws.title, ws.max_row, ws.max_column, hidden=ws.sheet_state != "visible")
                for ws in self._openpyxl.worksheets]

    def reader_for(self, sheet: SheetInfo):
        if sheet.cells is not None and sheet.cells <= self.cell_budget:
            return "calamine"
        return "openpyxl"

    def rows(self, sheet: SheetInfo):
        """Yield normalised row tuples for one sheet."""
        if self.reader_for(sheet) == "calamine":
            yield from self._calamine_rows(sheet)[0]
        else:
            for row in self._openpyxl[sheet.name].iter_rows(values_only=True):
                yield tuple(_normalise(v) for v in row)

    def grid(self, sheet: SheetInfo):
        """
        The whole sheet as a list of rows, plus the 0-based Excel column of the rows'
        first cell (calamine skips empty columns on the left). Calamine sheets only.
        """
        rows, first_col = self._calamine_rows(sheet)
        return list(rows), first_col

    def _calamine_rows(self, sheet):
        if self._calamine is None:
            self._calamine = CalamineWorkbook.from_path(self.path)
        cs = self._calamine.get_sheet_by_name(sheet.name)
        rows = (tuple(_normalise(v) for v in row) for row in cs.iter_rows())
        # calamine yields rows from Excel row 1, but columns from the first used column.
        first_col = cs.start[1] if cs.start else 0
        return _fill_merged_down(rows, cs.merged_cell_ranges or [], (0, first_col)), first_col

    def close(self):
        self._openpyxl.close()


def _fill_merged_down(rows, merges, origin):
    """
    Repeat the top cell of each row-spanning merge in the cells below it.

    `merges` are ((first_row, first_col), (last_row, last_col)) in absolute 0-based
    coordinates; `rows` start at `origin` (row, column).
    """
    r0, c0 = origin
    below = {}                      # row -> [(col, row of the merge's top cell)]
    tops = {}                       # row -> [col] whose value must be remembered
    for (r1, c1), (r2, _) in merges:
        if r2 > r1:
            tops.setdefault(r1 - r0, []).append(c1 - c0)
            for r in range(r1 + 1, r2 + 1):
                below.setdefault(r - r0, []).append((c1 - c0, r1 - r0))
    kept = {}
    for i, row in enumerate(rows):
        if i in below:
            row = list(row)
            for col, top in below[i]:
                if 0 <= col < len(row) and row[col] is None:
                    row[col] = kept.get((top, col))
            row = tuple(row)
        for col in tops.get(i, ()):
            kept[(i, col)] = row[col] if 0 <= col < len(row) else None
        yield row


def _normalise(v):
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    if isinstance(v, dt.datetime) and v.time() == dt.time(0):
        return v.date()
    return v
