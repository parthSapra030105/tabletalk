"""
What the model learns about where each table came from, and how its values are stored:
hidden sheets, titles, codes kept as text, and percentages stored as fractions of 1.
The last test needs the database from scripts/setup_db.py.
"""

import os
from pathlib import Path

import openpyxl
import psycopg
import pytest
from dotenv import load_dotenv

from catalog.describe import table_profile
from catalog.render import column_details, compact_index
from ingest.pipeline import ingest_workbook
from ingest.values import ColumnType

load_dotenv(Path(__file__).resolve().parents[2] / ".env")
APP_URL = os.environ.get("DATABASE_URL")


def _plan_workbook(path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Plan"
    ws.append(["Meta plan"])
    ws.append(["market", "pincode", "reach %", "budget"])
    ws.append(["Pune", 411001, 0.25, 1000])
    ws.append(["Surat", 395007, 0.4, 2000])
    ws.append(["Thane", 400601, 0.1, 500])
    old = wb.create_sheet("Old plan")
    old.append(["market", "budget"])
    old.append(["Pune", 900])
    old.append(["Surat", 1800])
    old.sheet_state = "hidden"
    wb.save(path)
    return path


def test_whole_numbers_in_a_text_column_lose_the_excel_decimal():
    assert ColumnType("text").coerce(411001.0) == ("411001", False)
    assert ColumnType("text").coerce(2.5) == ("2.5", False)


def test_pincodes_are_text_and_hidden_sheets_are_flagged(tmp_path):
    plan, old = ingest_workbook(_plan_workbook(tmp_path / "wb.xlsx"))
    pincode = next(c for c in plan.columns if c.name == "pincode")
    assert pincode.type == "text" and pincode.coercion_failures == 0
    assert (plan.hidden, old.hidden) == (False, True)
    assert plan.title == "Meta plan"


def _catalog():
    return {"schema": "ds_x", "joins": [], "tables": [
        {"name": "plan", "sheet": "Plan", "row_count": 3, "title": "Meta plan", "range": "A1:D5",
         "columns": [{"name": "reach_pct", "original": "reach %", "type": "numeric", "null_pct": 0, "distinct": 3,
                      "min": 0.1, "max": 0.4, "fraction": True, "description": "Share of the audience reached"}]},
        {"name": "old_plan", "sheet": "Old plan", "row_count": 2, "hidden": True,
         "columns": [{"name": "budget", "original": "budget", "type": "numeric", "null_pct": 0, "distinct": 2,
                      "min": 900, "max": 1800}]},
    ]}


def test_the_index_marks_hidden_sheets_and_fractions_but_holds_no_cell_text():
    index = compact_index(_catalog())
    assert "old_plan (2 rows, hidden sheet)" in index
    assert "reach_pct (num, fraction of 1)" in index
    assert "Meta plan" not in index          # a title is cell text: only inside <data>


def test_column_details_carry_the_title_and_the_fraction_inside_the_data_block():
    details = column_details(_catalog(), {"plan": ["reach_pct"]})
    data = details.split("<data>", 1)[1]
    assert 'titled "Meta plan" on sheet "Plan"' in data
    assert "stored as a fraction: 0.25 means 25%" in data


def test_the_describe_profile_includes_title_and_hidden():
    profile = table_profile(_catalog()["tables"][1])
    assert profile["hidden"] is True
    assert table_profile(_catalog()["tables"][0])["columns"][0]["stored_as"].startswith("fraction")


@pytest.mark.skipif(not APP_URL, reason="run scripts/setup_db.py first")
def test_parallel_tables_are_not_joined_but_a_lookup_table_is(tmp_path):
    from ingest.postgres import load_workbook

    cities = [f"City {i}" for i in range(12)]
    wb = openpyxl.Workbook()
    for title, header, rows in (
        ("Plan A", ["city", "market", "budget"], [[c, "P1", 100 + i] for i, c in enumerate(cities)]),
        ("Plan B", ["city", "market", "budget"], [[c, "P2", 200 + i] for i, c in enumerate(cities)]),
        ("Cities", ["city", "state"], [[c, "MH"] for c in cities]),
        ("Orders", ["order_ref", "city", "amount"], [[f"O{i}", cities[i % 12], i] for i in range(30)]),
    ):
        ws = wb.create_sheet(title)
        ws.append(header)
        for row in rows:
            ws.append(row)
    del wb["Sheet"]
    wb.save(tmp_path / "wb.xlsx")

    schema = "ds_parallel_test"
    with psycopg.connect(APP_URL, autocommit=True) as conn:
        conn.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
    try:
        _, _, catalog = load_workbook(tmp_path / "wb.xlsx", dsn=APP_URL, schema=schema)
        pairs = {(j["from_table"], j["to_table"]) for j in catalog["joins"]}
        assert ("orders", "cities") in pairs
        assert not pairs & {("plan_a", "plan_b"), ("plan_b", "plan_a")}
    finally:
        with psycopg.connect(APP_URL, autocommit=True) as conn:
            conn.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")


@pytest.mark.skipif(not APP_URL, reason="run scripts/setup_db.py first")
def test_the_built_catalog_records_where_each_table_came_from(tmp_path):
    from ingest.postgres import load_workbook

    schema = "ds_provenance_test"
    with psycopg.connect(APP_URL, autocommit=True) as conn:
        conn.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
    try:
        _, _, catalog = load_workbook(_plan_workbook(tmp_path / "wb.xlsx"), dsn=APP_URL, schema=schema)
        plan, old = catalog["tables"]
        assert (plan["title"], plan["range"]) == ("Meta plan", "A1:D5")
        assert old["hidden"] is True and "hidden" not in plan
        columns = {c["name"]: c for c in plan["columns"]}
        assert columns["reach_pct"].get("fraction") is True
        assert not columns["budget"].get("fraction")
        assert columns["pincode"]["type"] == "text"
        with psycopg.connect(APP_URL) as conn:
            assert conn.execute(f"SELECT pincode FROM {schema}.plan ORDER BY 1").fetchone()[0] == "395007"
    finally:
        with psycopg.connect(APP_URL, autocommit=True) as conn:
            conn.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
