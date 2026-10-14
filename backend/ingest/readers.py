"""
Read rows from an .xlsx sheet, choosing the reader by sheet size.

- python-calamine: fast (Rust), but loads the whole sheet into memory first.
- openpyxl read-only: streams row by row with flat memory, but is several times slower.

The size check uses the sheet's <dimension> metadata via openpyxl, which costs
almost nothing. Sheets under CELL_BUDGET go to calamine; bigger ones, or ones with
no dimension recorded, are streamed. Both readers yield rows in one shape:
a tuple of Python values, with empty cells as None and midnight datetimes as dates.
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
        return [SheetInfo(ws.title, ws.max_row, ws.max_column) for ws in self._openpyxl.worksheets]

    def reader_for(self, sheet: SheetInfo):
        if sheet.cells is not None and sheet.cells <= self.cell_budget:
            return "calamine"
        return "openpyxl"

    def rows(self, sheet: SheetInfo):
        """Yield normalised row tuples for one sheet."""
        if self.reader_for(sheet) == "calamine":
            if self._calamine is None:
                self._calamine = CalamineWorkbook.from_path(self.path)
            raw = self._calamine.get_sheet_by_name(sheet.name).iter_rows()
        else:
            raw = self._openpyxl[sheet.name].iter_rows(values_only=True)
        for row in raw:
            yield tuple(_normalise(v) for v in row)

    def close(self):
        self._openpyxl.close()


def _normalise(v):
    if v is None or v == "":
        return None
    if isinstance(v, dt.datetime) and v.time() == dt.time(0):
        return v.date()
    return v
