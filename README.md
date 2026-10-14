# Tabletalk

Chat with a large, messy Excel workbook. Ask questions in plain language and get answers built from real query results.

> Work in progress.

## Setup

Requires Python 3.14.

```bash
python -m venv .venv
.venv/Scripts/activate        # Windows; use `source .venv/bin/activate` on macOS/Linux
pip install -r requirements.txt
```

## Test workbook

```bash
python scripts/generate_workbook.py                                    # full size -> data/tabletalk_sample.xlsx
python scripts/generate_workbook.py --scale 0.01 --out data/dev.xlsx   # ~10k rows, for quick dev runs
```

The workbook is an Indian D2C electronics retailer from Apr 2024 to Mar 2026. It has five related sheets (Orders, Customers, Products, Returns, and a wide Customer_360 sheet with 86 columns), with deliberately messy headers and values and a few planted stories. Each run also writes `*_answer_key.json`, which holds the true figures recomputed from the clean data. The same `--seed` always produces the same file.

Full-size run on a laptop (seed 42):

| Step | Time |
|---|---|
| Generate clean tables (numpy) | 3.5 s |
| Mess layer | 4.1 s |
| Write .xlsx (xlsxwriter, constant_memory) | 179.7 s |
| **Total** | **~3 min 10 s** for 1,001,423 rows, 93.7 MB |
