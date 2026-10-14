"""Find the real header row in a sheet and turn its labels into safe SQL names."""

import re

HEADER_SCAN_ROWS = 20

# Words that would force the model to quote a column name in every query.
SQL_RESERVED = {"order", "group", "select", "from", "where", "table", "user", "limit", "offset",
                "join", "by", "to", "and", "or", "not", "case", "when", "end", "desc", "asc", "all", "check"}


def find_header(rows):
    """
    Index of the header within the first rows of a sheet, or None.

    Title rows have one filled cell and spacer rows have none. The header is the
    first row that is at least half as full as the fullest row in the window,
    mostly text, and followed by a row that has data.
    """
    window = rows[:HEADER_SCAN_ROWS]
    filled = [sum(v is not None for v in row) for row in window]
    if not filled or max(filled) < 2:
        return None
    widest = max(filled)
    for i, row in enumerate(window):
        if filled[i] < max(2, widest / 2):
            continue
        texts = sum(isinstance(v, str) for v in row if v is not None)
        has_data_after = any(filled[j] > 0 for j in range(i + 1, len(window)))
        if texts / filled[i] >= 0.8 and has_data_after:
            return i
    return None


def clean_name(label, position):
    """'Sales Amt (₹) Apr-24' -> 'sales_amt_apr_24'; a blank label -> 'column_<n>'."""
    if label is None or str(label).strip() == "":
        return f"column_{position + 1}"
    s = str(label).strip().lower()
    s = s.replace("%", " pct ").replace("#", " num ").replace("&", " and ")
    s = re.sub(r"[₹$€£]", " ", s)
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    if not s:
        return f"column_{position + 1}"
    if s[0].isdigit():
        s = "c_" + s
    if s in SQL_RESERVED:
        s += "_col"
    return s[:60]          # Postgres truncates identifiers at 63 bytes


def unique_names(names):
    """['status', 'status'] -> ['status', 'status_2']."""
    seen, out = {}, []
    for n in names:
        if n in seen:
            seen[n] += 1
            candidate = f"{n}_{seen[n]}"
            while candidate in seen:
                seen[n] += 1
                candidate = f"{n}_{seen[n]}"
            seen[candidate] = 1
            out.append(candidate)
        else:
            seen[n] = 1
            out.append(n)
    return out
