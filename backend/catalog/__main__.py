"""
Add LLM descriptions to a saved catalog JSON (written by `python -m ingest ... --load`).

    cd backend
    python -m catalog describe ../data/tabletalk_sample_ds_1_catalog.json
    python -m catalog index ../data/tabletalk_sample_ds_1_catalog.json      # print the compact index and its size
"""

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from .describe import describe_catalog
from .render import column_details, compact_index, count_tokens


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["describe", "index"])
    parser.add_argument("catalog")
    args = parser.parse_args()

    path = Path(args.catalog)
    catalog = json.loads(path.read_text(encoding="utf-8"))
    if args.command == "index":
        show_index(catalog)
        return
    usages = describe_catalog(catalog)
    path.write_text(json.dumps(catalog, indent=2, ensure_ascii=False), encoding="utf-8")

    for t in catalog["tables"]:
        if "description_error" in t:
            print(f"{t['name']}: FAILED {t['description_error']}")
            continue
        missing = t["undescribed_columns"]
        print(f"{t['name']}: {t['description']}")
        print(f"  {len(t['columns']) - len(missing)}/{len(t['columns'])} columns described"
              + (f", missing: {missing}" if missing else ""))
        for a in t["ambiguities"]:
            print(f"  ambiguous {a['columns']}: {a['note']}")
    print("\ncall                    prompt  output   total  seconds")
    for u in usages:
        print(f"{u['purpose']:<22} {u['prompt_tokens']:>7} {u['completion_tokens']:>7} {u['total_tokens']:>7} {u['seconds']:>8}")
    print(f"{'all tables':<22} {sum(u['prompt_tokens'] for u in usages):>7} "
          f"{sum(u['completion_tokens'] for u in usages):>7} {sum(u['total_tokens'] for u in usages):>7}")


def show_index(catalog):
    index = compact_index(catalog)
    print(index)
    # A typical pick for "revenue by customer city": what the SQL node would get on top of the index.
    example = column_details(catalog, {"orders": ["cust_id", "net_amount", "gross_amount", "status"],
                                       "customers": ["customerid", "city"]})
    full = json.dumps(catalog, ensure_ascii=False)
    print("\n--- example column details ---\n" + example)
    print("\nestimated tokens (o200k):")
    print(f"  whole catalog as JSON (the dump-everything approach): {count_tokens(full):>6,}")
    print(f"  compact index (always sent):                          {count_tokens(index):>6,}")
    print(f"  column details for the example pick:                  {count_tokens(example):>6,}")


if __name__ == "__main__":
    main()
