"""
Find the tables on a hand-made sheet.

People put several tables on one sheet: side by side, stacked with blank rows in
between, with a title or a few "Client: ..." lines above each one, and notes typed
around them. This splits a sheet's grid (a list of row tuples, empty cells as None)
into blocks, one per table, before anything is typed or loaded.

1. Regions (XY-cut): split the sheet at fully blank rows, split each part at fully
   empty columns, and repeat inside each part until nothing splits. "Empty" is judged
   inside each part, so a stray cell elsewhere on the sheet can't glue two tables together.
   Two regions covering exactly the same rows, one or two empty columns apart, are one
   table with a spacer column, and are joined back.
2. Tables: a region with a header row starts a table; rows above the header are its
   title. A small text-only region (at most 2 columns and 6 rows) right above a table
   is that table's title too ("Client: Acme"). Title lines starting with "*" are
   footnotes and become notes. A region without a header continues the table above it,
   which is how blank rows inside a table are handled. A single column of text is a list:
   its first cell, or the label above it, is the header, and a list split by blank rows
   stays one list.
3. Notes: a row with a single text cell, a column with no header and fewer than three
   values, and a column with nothing under its header are dropped and kept as notes.
   Regions that are none of the above are reported as leftovers.
"""

from dataclasses import dataclass, field

from .headers import find_header

PREAMBLE_MAX_COLS = 2
PREAMBLE_MAX_ROWS = 6
LIST_MIN_VALUES = 3
SPARSE_COLUMN_VALUES = 3          # a headerless column with fewer values than this is notes
SPACER_MAX_COLS = 2               # empty columns a table can have inside it
MAX_NOTES = 10


@dataclass
class Region:
    top: int          # rows and columns are 0-based grid indices; bottom and right are exclusive
    bottom: int
    left: int
    right: int


@dataclass
class Block:
    """One table found on a sheet. `rows` and `skipped` hold grid row indices."""
    left: int
    right: int
    top: int                                       # first row of the block, title included
    header_row: int
    header: tuple
    columns: list                                  # grid column indices kept
    rows: list = field(default_factory=list)       # candidate data rows, in order
    skipped: list = field(default_factory=list)    # (grid row, reason)
    title: list = field(default_factory=list)      # title lines
    notes: list = field(default_factory=list)
    bottom: int = 0                                # exclusive


def find_blocks(grid):
    """Split a sheet's grid into tables. Returns (blocks, leftover regions)."""
    width = max((len(r) for r in grid), default=0)
    grid = [r if len(r) == width else tuple(r) + (None,) * (width - len(r)) for r in grid]
    regions = []
    _cut(grid, Region(0, len(grid), 0, width), regions)
    regions = _join_spacers(regions)

    headers = [_header_index(grid, r) for r in regions]
    titles = {}                     # region index -> title lines from a preamble region above it
    used = set()
    for i, r in enumerate(regions):
        # A preamble can look like a header row ("Client | Acme"), so check it first. A list long
        # enough to stand on its own is the start of a list, not a label.
        if _is_preamble(grid, r) and not (_is_list(r) and headers[i] is not None):
            target = _table_below(regions, headers, i)
            if target is not None:
                titles.setdefault(target, []).extend(_text_lines(grid, r))
                used.add(i)

    blocks, leftovers = [], []
    for i, r in enumerate(regions):
        if i in used:
            continue
        above = _block_above(blocks, r)
        if headers[i] is not None and i not in titles and _is_list(r) and above and _is_list(above):
            _continue_block(grid, above, r)         # the next stretch of a list split by blank rows
        elif headers[i] == r.top and i not in titles and above and _like_data_above(grid, above, r.top):
            _continue_block(grid, above, r)         # a text-heavy data row after a blank row, not a header
        elif headers[i] is not None:
            blocks.append(_new_block(grid, r, headers[i], titles.get(i, [])))
        elif above is not None:
            _continue_block(grid, above, r)
        else:
            leftovers.append(r)

    tables = []
    for b in blocks:
        _finish(grid, b)
        # A one-row, two-column scrap next to real tables is a note; alone on its sheet, it's the data.
        tiny = len(b.rows) < 2 and len(b.columns) < 3
        if b.rows and (not tiny or len(blocks) == 1):
            tables.append(b)
        else:
            leftovers.append(Region(b.top, b.bottom, b.left, b.right))
    return tables, leftovers


# --- regions -------------------------------------------------------------------------

def _cut(grid, region, out):
    width = region.right - region.left
    rows = [i for i in range(region.top, region.bottom) if grid[i][region.left:region.right].count(None) != width]
    if not rows:
        return
    cols = [c for c in range(region.left, region.right) if any(grid[i][c] is not None for i in rows)]
    top, bottom, left, right = rows[0], rows[-1] + 1, cols[0], cols[-1] + 1
    row_runs = _runs(rows)
    if len(row_runs) > 1:
        for a, b in row_runs:
            _cut(grid, Region(a, b, left, right), out)
        return
    col_runs = _runs(cols)
    if len(col_runs) > 1:
        for a, b in col_runs:
            _cut(grid, Region(top, bottom, a, b), out)
        return
    out.append(Region(top, bottom, left, right))


def _runs(indices):
    """[1, 2, 3, 7, 8] -> [(1, 4), (7, 9)]"""
    runs, start = [], indices[0]
    for prev, cur in zip(indices, indices[1:]):
        if cur != prev + 1:
            runs.append((start, prev + 1))
            start = cur
    runs.append((start, indices[-1] + 1))
    return runs


def _join_spacers(regions):
    out = []
    for r in regions:
        last = out[-1] if out else None
        if last and (last.top, last.bottom) == (r.top, r.bottom) and 0 < r.left - last.right <= SPACER_MAX_COLS:
            out[-1] = Region(last.top, last.bottom, last.left, r.right)
        else:
            out.append(r)
    return out


def _cells(grid, region, row):
    return grid[row][region.left:region.right]


def _header_index(grid, region):
    """Grid row of the region's header, or None. A single column of text is a list headed by its first cell."""
    if region.right - region.left == 1:
        values = [grid[i][region.left] for i in range(region.top, region.bottom)]
        filled = [v for v in values if v is not None]
        if len(filled) > LIST_MIN_VALUES and all(isinstance(v, str) for v in filled):
            return region.top + values.index(filled[0])
        return None
    h = find_header([_cells(grid, region, i) for i in range(region.top, region.bottom)])
    return None if h is None else region.top + h


def _is_list(area):
    """A region or block one column wide."""
    return area.right - area.left == 1


def _is_preamble(grid, region):
    if region.right - region.left > PREAMBLE_MAX_COLS or region.bottom - region.top > PREAMBLE_MAX_ROWS:
        return False
    values = [v for i in range(region.top, region.bottom) for v in _cells(grid, region, i) if v is not None]
    return bool(values) and all(isinstance(v, str) for v in values)


def _overlaps(a_left, a_right, b_left, b_right):
    return a_left < b_right and b_left < a_right


def _table_below(regions, headers, i):
    """The nearest region below region i, sharing columns with it, if that region has a header."""
    r = regions[i]
    below = [j for j, o in enumerate(regions) if o.top >= r.bottom and _overlaps(r.left, r.right, o.left, o.right)]
    if not below:
        return None
    j = min(below, key=lambda j: regions[j].top)
    return j if headers[j] is not None else None


def _text_lines(grid, region):
    lines = []
    for i in range(region.top, region.bottom):
        texts = [str(v).strip() for v in _cells(grid, region, i) if isinstance(v, str)]
        if texts:
            lines.append(": ".join(texts) if len(texts) == 2 else " ".join(texts))
    return lines


# --- blocks --------------------------------------------------------------------------

def _new_block(grid, region, h, preamble):
    width = region.right - region.left
    if width == 1 and preamble:
        # A list under a label: the label is the header, and every cell is a value.
        header, rows = (preamble[-1],), list(range(region.top, region.bottom))
        title = preamble[:-1]
    else:
        header, rows = _cells(grid, region, h), list(range(h + 1, region.bottom))
        title = preamble + _text_lines(grid, Region(region.top, h, region.left, region.right))
    # "*rates are indicative" above a table is a footnote, not its title.
    notes = [t for t in title if t.startswith("*")]
    title = [t for t in title if not t.startswith("*")]
    return Block(left=region.left, right=region.right, top=region.top, header_row=h, header=header,
                 columns=list(range(region.left, region.right)), rows=rows, title=title, notes=notes,
                 bottom=region.bottom)


def _block_above(blocks, region):
    candidates = [b for b in blocks if b.bottom <= region.top and _overlaps(b.left, b.right, region.left, region.right)]
    return max(candidates, key=lambda b: b.bottom) if candidates else None


def _like_data_above(grid, block, row):
    """Does this row hold the same kinds of values, column by column, as the block's last data row?"""
    last = next((i for i in reversed(block.rows) if sum(v is not None for v in grid[i][block.left:block.right]) > 1),
                None)
    if last is None:
        return False
    pairs = [(_kind(a), _kind(b)) for a, b in zip(grid[last][block.left:block.right], grid[row][block.left:block.right])
             if a is not None and b is not None]
    return bool(pairs) and sum(a == b for a, b in pairs) / len(pairs) >= 0.8


def _kind(v):
    if isinstance(v, str):
        return "text"
    if isinstance(v, (int, float)):
        return "number"
    return type(v).__name__


def _continue_block(grid, block, region):
    block.skipped.extend((i, "blank row") for i in range(block.bottom, region.top))
    block.rows.extend(range(region.top, region.bottom))
    block.bottom = region.bottom
    outside = [v for i in range(region.top, region.bottom) for c in range(region.left, region.right)
               if not block.left <= c < block.right and (v := grid[i][c]) is not None]
    block.notes.extend(str(v) for v in outside if isinstance(v, str))


def _finish(grid, b):
    """Drop note rows, repeated headers and note columns from a block."""
    width = b.right - b.left
    header_values = tuple(_norm(v) for v in b.header)
    kept = []
    for i in b.rows:
        cells = grid[i][b.left:b.right]
        filled = [v for v in cells if v is not None]
        if not filled:
            b.skipped.append((i, "blank row"))
        elif width >= 3 and len(filled) == 1 and isinstance(filled[0], str):
            b.skipped.append((i, "note"))
            b.notes.append(filled[0])
        elif len(b.header) == width and tuple(_norm(v) for v in cells) == header_values:
            b.skipped.append((i, "repeated header row"))
        else:
            kept.append(i)
    b.rows = kept

    columns = []
    for c, label in zip(range(b.left, b.right), b.header):
        values = [grid[i][c] for i in b.rows if grid[i][c] is not None]
        if label is None and len(values) < SPARSE_COLUMN_VALUES:
            b.notes.extend(str(v) for v in values if isinstance(v, str))
        elif not values and len(b.header) > 1:
            if isinstance(label, str):             # a label or a sentence over an empty column
                b.notes.append(label)
        else:
            columns.append(c)
    b.columns = columns
    b.header = tuple(b.header[c - b.left] for c in columns)
    b.notes = [str(n).strip()[:200] for n in b.notes][:MAX_NOTES]


def _norm(v):
    return v.strip().lower() if isinstance(v, str) else v
