import datetime as dt

import pytest

from ingest.values import infer_type, is_null, parse_bool, parse_date, parse_number


@pytest.mark.parametrize("raw, expected", [
    (1250, 1250),
    (2879.1, 2879.1),
    ("1,24,500.00", 124500.0),
    ("₹6,499", 6499),
    ("$1,234.50", 1234.5),
    ("€ 99", 99),
    ("£1,000", 1000),
    ("Rs. 500", 500),
    ("INR 2,000", 2000),
    ("12%", 12),
    ("(1,234)", -1234),
    ("($50.25)", -50.25),
    ("-₹300", -300),
    ("0.75", 0.75),
])
def test_parse_number_accepts(raw, expected):
    assert parse_number(raw) == expected


@pytest.mark.parametrize("raw", [
    "+91 8274396623",   # phone number
    "0411",             # code with a leading zero
    "C100744",          # identifier
    "N/A",
    "North",
    True,
    "12 units",
])
def test_parse_number_rejects(raw):
    assert parse_number(raw) is None


def test_null_tokens():
    assert all(is_null(v) for v in [None, "", "  ", "N/A", "na", "-", "#N/A", "null"])
    assert not is_null("0") and not is_null(0)


def test_bools():
    assert [parse_bool(v) for v in ["Y", "no", "TRUE", True, "maybe"]] == [True, False, True, True, None]


def test_dates_in_several_formats():
    assert parse_date("15/03/2025") == dt.date(2025, 3, 15)
    assert parse_date("03/15/2025", day_first=False) == dt.date(2025, 3, 15)
    assert parse_date("2025-03-15") == dt.date(2025, 3, 15)
    assert parse_date("15-Mar-2025") == dt.date(2025, 3, 15)
    assert parse_date("Mar 15, 2025") == dt.date(2025, 3, 15)
    assert parse_date("31/02/2025") is None


def test_day_first_is_decided_per_column():
    assert infer_type(["13/01/2025", "02/03/2025"]).day_first is True
    assert infer_type(["01/13/2025", "02/03/2025"]).day_first is False
    ambiguous = infer_type(["01/02/2025", "03/04/2025"])
    assert ambiguous.day_first is True and ambiguous.ambiguous_day_month


def test_inferred_types():
    assert infer_type(["1,200", "₹3,400", 15, "(200)"]).sql_type == "numeric"
    assert infer_type(["Y", "N", "Yes"]).sql_type == "boolean"
    assert infer_type([dt.date(2025, 1, 1), "02/03/2025"]).sql_type == "date"
    assert infer_type(["+91 98200 00000", "9820000000"]).sql_type == "text"


def test_category_casing_is_merged():
    t = infer_type(["North", "north", " NORTH ", "North", "South", "south"])
    assert t.sql_type == "text"
    assert {t.coerce(v)[0] for v in ["NORTH", " north  ", "South"]} == {"North", "South"}
