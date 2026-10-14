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
python scripts/generate_workbook.py            # full size, ~1M rows -> data/tabletalk_sample.xlsx
python scripts/generate_workbook.py --scale 0.01   # ~10k rows, for quick dev runs
```
