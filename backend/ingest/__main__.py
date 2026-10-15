"""
Run the ingest pipeline on a workbook and print the summary.

    cd backend
    python -m ingest ../data/tabletalk_sample.xlsx --answer-key ../data/tabletalk_sample_answer_key.json          # dry run
    python -m ingest ../data/tabletalk_sample.xlsx --answer-key ../data/tabletalk_sample_answer_key.json --load   # into Postgres
"""

import argparse
import json
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from .pipeline import ingest_workbook


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("path")
    parser.add_argument("--answer-key", help="check rows loaded against the generator's expected counts")
    parser.add_argument("--columns", action="store_true", help="print every column, not just notable ones")
    parser.add_argument("--load", action="store_true", help="load into Postgres (DATABASE_URL from .env)")
    args = parser.parse_args()

    start = time.perf_counter()
    if args.load:
        from .postgres import load_workbook
        load_dotenv(Path(__file__).resolve().parents[2] / ".env")
        progress = lambda sheet, done, total: print(f"  {sheet}: {done:,} of ~{total or 0:,} rows", flush=True)
        schema, reports = load_workbook(args.path, progress=progress)
        print(f"\nloaded into schema {schema}")
    else:
        reports = ingest_workbook(args.path)
    total = time.perf_counter() - start

    expected = {}
    if args.answer_key:
        with open(args.answer_key, encoding="utf-8") as f:
            expected = json.load(f)["expected_ingest"]

    for r in reports:
        if r.status != "loaded":
            print(f"\n{r.sheet}: SKIPPED ({r.reason})")
            continue
        check = ""
        if r.sheet in expected:
            want = expected[r.sheet]["data_rows"]
            check = "  ✓ matches answer key" if want == r.rows_loaded else f"  ✗ answer key expects {want:,}"
        print(f"\n{r.sheet} -> {r.table}  [{r.reader}, header on row {r.header_row}, {r.seconds}s]")
        print(f"  rows loaded: {r.rows_loaded:,}{check}")
        for reason, s in r.skipped_rows.items():
            print(f"  skipped {s['count']:,} × {reason} (e.g. rows {', '.join(map(str, s['examples']))})")
        for c in r.columns:
            notable = c.coercion_failures or c.note or c.original != c.name
            if args.columns or notable:
                line = f"    {c.name:<24} {c.type:<9} from {c.original!r}"
                if c.coercion_failures:
                    line += f"  | {c.coercion_failures:,} failed, e.g. {c.failure_examples[:2]}"
                if c.note:
                    line += f"  | {c.note}"
                print(line)
    print(f"\ntotal {total:.1f}s")


if __name__ == "__main__":
    main()
