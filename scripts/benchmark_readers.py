"""
Benchmark ways of reading one large sheet from an .xlsx file: time and peak memory.

Each reader runs in its own child process, so one reader's memory can't affect
another's reading. The parent samples the child's resident memory (RSS) every
20 ms and reports the peak. Each reader only reads every row and counts it;
nothing else is done, so this measures the cost of reading and nothing more.

    python scripts/benchmark_readers.py data/tabletalk_sample.xlsx --sheet Orders
"""

import argparse
import json
import subprocess
import sys
import time

import psutil

READERS = ["openpyxl_readonly", "calamine_iter", "pandas_calamine", "pandas_openpyxl"]


def run_reader(name, path, sheet):
    """Runs inside the child process. Returns (rows read, seconds). Imports happen before the clock starts."""
    if name.startswith("pandas"):
        import pandas as pd
    elif name == "openpyxl_readonly":
        import openpyxl
    else:
        from python_calamine import CalamineWorkbook

    start = time.perf_counter()
    rows = 0
    if name == "pandas_openpyxl":
        rows = len(pd.read_excel(path, sheet_name=sheet, header=None, engine="openpyxl"))
    elif name == "pandas_calamine":
        rows = len(pd.read_excel(path, sheet_name=sheet, header=None, engine="calamine"))
    elif name == "openpyxl_readonly":
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        for _ in wb[sheet].iter_rows(values_only=True):
            rows += 1
        wb.close()
    elif name == "calamine_iter":
        for _ in CalamineWorkbook.from_path(path).get_sheet_by_name(sheet).iter_rows():
            rows += 1
    return rows, time.perf_counter() - start


def measure(name, path, sheet):
    """Runs in the parent: start the child, track its peak memory, collect its result."""
    child = subprocess.Popen([sys.executable, __file__, path, "--sheet", sheet, "--child", name],
                             stdout=subprocess.PIPE, text=True)
    proc = psutil.Process(child.pid)
    peak = 0
    while child.poll() is None:
        try:
            # Sum over the process tree: a virtualenv's python can be a launcher that runs the real interpreter as a child.
            tree = [proc] + proc.children(recursive=True)
            peak = max(peak, sum(p.memory_info().rss for p in tree))
        except psutil.NoSuchProcess:
            pass
        time.sleep(0.02)
    result = json.loads(child.stdout.read())
    result.update(reader=name, peak_mb=round(peak / 1e6))
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("path")
    parser.add_argument("--sheet", default="Orders")
    parser.add_argument("--readers", nargs="+", default=READERS, choices=READERS)
    parser.add_argument("--child", help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.child:
        rows, secs = run_reader(args.child, args.path, args.sheet)
        print(json.dumps({"rows": rows, "seconds": round(secs, 2)}))
        return

    print(f"{'reader':<20} {'rows':>9} {'seconds':>8} {'rows/s':>9} {'peak MB':>8}")
    for name in args.readers:
        r = measure(name, args.path, args.sheet)
        print(f"{r['reader']:<20} {r['rows']:>9,} {r['seconds']:>8} {r['rows'] / r['seconds']:>9,.0f} {r['peak_mb']:>8,}",
              flush=True)


if __name__ == "__main__":
    main()
