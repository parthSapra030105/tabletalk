"""
Type inference and value coercion.

A column's type is inferred once, from a sample of its values. Every value is then
coerced to that type. A value that doesn't fit becomes NULL and is counted as a
coercion failure; the row is kept, and the failure is reported.
"""

import datetime as dt
import re
from collections import Counter
from dataclasses import dataclass, field

NULL_TOKENS = {"n/a", "na", "-", "--", "_", "null", "none", "nil", "#n/a", "#value!", "#div/0!", "#ref!", "?"}
TRUE_TOKENS = {"y", "yes", "true"}
FALSE_TOKENS = {"n", "no", "false"}
TYPE_THRESHOLD = 0.95            # share of sample values that must parse for a column to get the type

CATEGORY_MAX_DISTINCT = 50       # text columns with at most this many distinct values get casing merged

_NUMBER = re.compile(r"^-?\d+(\.\d+)?$")
_YMD = re.compile(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$")
_YMD_TIME = re.compile(r"^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?$")
_AB_Y = re.compile(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})$")            # 03/04/2025: day or month first?
_D_MON_Y = re.compile(r"^(\d{1,2})[-\s]([A-Za-z]{3,9})[-\s,]+(\d{4})$")  # 15-Mar-2025
_MON_D_Y = re.compile(r"^([A-Za-z]{3,9})\s+(\d{1,2}),?\s+(\d{4})$")     # Mar 15, 2025
_MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun",
                                        "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}


_NULLS = NULL_TOKENS | {""}
_CURRENCY = re.compile(r"[₹$€£]|\b(?:rs\.?|inr|usd|eur|gbp)(?=\s|\d|$)", re.IGNORECASE)


def is_null(v):
    return v is None or (isinstance(v, str) and v.strip().lower() in _NULLS)


def parse_number(v):
    """
    Numbers as Excel stores them, or as text: '1,24,500.00', '₹6,499', '$1,234',
    'Rs. 500', '12%', and '(1,234)' for an accounting-style negative.
    Returns int / float, or None if it isn't a number.
    """
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return v
    if not isinstance(v, str):
        return None
    s = v.strip()
    # A leading '+' means an identifier such as a phone number, not a quantity.
    if s.startswith("+"):
        return None
    negative = s.startswith("(") and s.endswith(")")
    if negative:
        s = s[1:-1]
    s = _CURRENCY.sub("", s).replace(",", "").replace(" ", "").removesuffix("%")
    # A leading zero (0123, 007) means a code or pincode, not a quantity.
    if len(s) > 1 and s[0] == "0" and s[1].isdigit():
        return None
    if not _NUMBER.match(s):
        return None
    n = float(s) if "." in s else int(s)
    return -n if negative else n


def parse_bool(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        s = v.strip().lower()
        if s in TRUE_TOKENS:
            return True
        if s in FALSE_TOKENS:
            return False
    return None


def _month(name):
    return _MONTHS.get(name[:3].lower())


def parse_date(v, day_first=True):
    """date / datetime / text in a known format -> date or datetime; anything else -> None."""
    if isinstance(v, (dt.date, dt.datetime)):
        return v
    if not isinstance(v, str):
        return None
    s = v.strip()
    try:
        if m := _YMD.match(s):
            return dt.date(int(m[1]), int(m[2]), int(m[3]))
        if m := _AB_Y.match(s):
            a, b = int(m[1]), int(m[2])
            day, month = (a, b) if day_first else (b, a)
            return dt.date(int(m[3]), month, day)
        if m := _D_MON_Y.match(s):
            return dt.date(int(m[3]), _month(m[2]), int(m[1])) if _month(m[2]) else None
        if m := _MON_D_Y.match(s):
            return dt.date(int(m[3]), _month(m[1]), int(m[2])) if _month(m[1]) else None
        if m := _YMD_TIME.match(s):
            return dt.datetime(int(m[1]), int(m[2]), int(m[3]), int(m[4]), int(m[5]), int(m[6] or 0))
    except ValueError:            # e.g. 31/02/2025
        return None
    return None


@dataclass
class ColumnType:
    sql_type: str                  # boolean | numeric | date | timestamp | text
    day_first: bool = True
    ambiguous_day_month: bool = False
    categories: dict = field(default_factory=dict)   # casefold key -> canonical spelling (text columns only)

    def coerce(self, v):
        """Returns (value, failed)."""
        if is_null(v):
            return None, False
        t = self.sql_type
        if t == "text":
            s = " ".join(str(v).split())
            if self.categories:
                key = s.casefold()
                s = self.categories.setdefault(key, s)
            return s, False
        if t == "numeric":
            n = parse_number(v)
            if n is None:
                return None, True
            return (int(n) if float(n).is_integer() else n), False
        if t == "boolean":
            b = parse_bool(v)
            return (b, False) if b is not None else (None, True)
        d = parse_date(v, self.day_first)
        if d is None:
            return None, True
        if t == "date":
            return (d.date() if isinstance(d, dt.datetime) else d), False
        return d, False


def infer_type(values):
    """Pick a ColumnType from sample values (nulls already removed)."""
    if not values:
        return ColumnType("text")
    n = len(values)

    if all(parse_bool(v) is not None for v in values):
        return ColumnType("boolean")

    numbers = [parse_number(v) for v in values]
    ok = [x for x in numbers if x is not None]
    if len(ok) / n >= TYPE_THRESHOLD:
        # One numeric type for all numbers: a whole-number sample can't later reject a decimal,
        # and sums of money stay exact.
        return ColumnType("numeric")

    day_first, ambiguous = _day_first(values)
    dates = [parse_date(v, day_first) for v in values]
    ok = [d for d in dates if d is not None]
    if len(ok) / n >= TYPE_THRESHOLD:
        has_time = any(isinstance(d, dt.datetime) and d.time() != dt.time(0) for d in ok)
        return ColumnType("timestamp" if has_time else "date", day_first=day_first, ambiguous_day_month=ambiguous)

    return ColumnType("text", categories=_categories(values))


def _day_first(values):
    """
    Decide DD/MM vs MM/DD once for the whole column. A first part over 12 proves
    day-first; a second part over 12 proves month-first. If nothing proves either,
    default to day-first and flag the column as ambiguous.
    """
    first = second = 0
    for v in values:
        if isinstance(v, str) and (m := _AB_Y.match(v.strip())):
            first, second = max(first, int(m[1])), max(second, int(m[2]))
    if first > 12:
        return True, False
    if second > 12:
        return False, False
    return True, first > 0


def _categories(values):
    """
    For low-cardinality text, map every spelling to one canonical form:
    'north', ' North ', 'NORTH' -> 'North'. The canonical form is the most
    common spelling in the sample, preferring one that isn't all lower or all upper case.
    """
    spellings = Counter(" ".join(str(v).split()) for v in values)
    by_key = {}
    for s, count in spellings.items():
        by_key.setdefault(s.casefold(), []).append((s, count))
    if len(by_key) > CATEGORY_MAX_DISTINCT or len(by_key) == len(values):
        return {}
    canonical = {}
    for key, options in by_key.items():
        options.sort(key=lambda sc: (sc[0] not in (sc[0].lower(), sc[0].upper()), sc[1]), reverse=True)
        canonical[key] = options[0][0]
    return canonical
