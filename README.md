# Tabletalk

Chat with a large, messy Excel workbook. Ask questions in plain language and get answers built from real query results.

> Work in progress.

## Setup

Requires Python 3.14.

```bash
python -m venv .venv
.venv/Scripts/activate        # Windows; use `source .venv/bin/activate` on macOS/Linux
pip install -r requirements.txt
python scripts/setup_db.py    # once: needs a local PostgreSQL superuser; writes .env
```

`setup_db.py` creates the `tabletalk` database and two roles:
- **`tabletalk_app`** loads data. It is the only role that can write.
- **`tabletalk_reader`** runs every model-written query. It is read-only at the role level, has a 10s statement timeout, can't see the app's own tables, and can't create temp tables.

```bash
cd backend && python -m pytest    # includes tests that try to write through the reader role
```

## Test workbook

```bash
python scripts/generate_workbook.py                                    # full size -> data/tabletalk_sample.xlsx
python scripts/generate_workbook.py --scale 0.01 --out data/dev.xlsx   # ~10k rows, for quick dev runs
```

The workbook is an Indian D2C electronics retailer from Apr 2024 to Mar 2026. It has five related sheets (Orders, Customers, Products, Returns, and a wide Customer_360 sheet with 86 columns), with deliberately messy headers and values and a few planted stories. Each run also writes `*_answer_key.json`, which holds the true figures recomputed from the clean data. The same `--seed` always produces the same file.

Full-size run (seed 42):

| Step | Time |
|---|---|
| Generate clean tables (numpy) | 3.5 s |
| Mess layer | 4.1 s |
| Write .xlsx (xlsxwriter, constant_memory) | 179.7 s |
| **Total** | **~3 min 10 s** for 1,001,423 rows, 93.7 MB |

## Reading large sheets

`scripts/benchmark_readers.py` reads one sheet with four readers. Each runs in its own process, and the script records wall time and peak memory. Results on the 600,049-row Orders sheet (15 columns):

| Reader | Seconds | Rows/s | Peak memory |
|---|---|---|---|
| openpyxl, read-only streaming | 117.4 | 5,112 | 97 MB |
| python-calamine `iter_rows` | 13.8 | 43,640 | 789 MB |
| pandas + calamine | 21.0 | 28,615 | 1,411 MB |
| pandas + openpyxl (the usual first attempt) | 134.1 | 4,475 | 816 MB |

```bash
python scripts/benchmark_readers.py data/tabletalk_sample.xlsx --sheet Orders
```

## Ingestion

```bash
cd backend
python -m ingest ../data/tabletalk_sample.xlsx --answer-key ../data/tabletalk_sample_answer_key.json          # dry run
python -m ingest ../data/tabletalk_sample.xlsx --answer-key ../data/tabletalk_sample_answer_key.json --load   # into Postgres
```

Each upload gets its own schema (`ds_1`, `ds_2`, …) with one table per sheet. Rows stream in through `COPY`, and the whole workbook loads in a single transaction, so a failed upload leaves nothing behind.

Full sample workbook (1,001,375 rows kept, 49 junk rows skipped), loaded into Postgres:

| Sheet | Rows | Columns | Skipped | Seconds |
|---|---|---|---|---|
| Orders | 600,000 | 15 | 5 blank, 40 duplicate, 1 total row | 43.5 |
| Customers | 250,000 | 10 | 3 blank | 10.7 |
| Products | 2,000 | 6 | – | 0.1 |
| Returns | 59,375 | 6 | – | 2.4 |
| Customer_360 | 90,000 | 86 | – | 23.9 |
| **Total** | **1,001,375** | | | **81.0** |

Reading the file and cleaning values take about 63 s of that; `COPY` adds about 18 s.

In the same transaction, the catalog step profiles every column, detects keys and joins, and adds indexes. It takes another 43.7 s (24.9 s profiling, 18.8 s keys, joins and indexes), for **127.4 s end to end**. All four joins in the sample (`orders.cust_id → customers.customerid`, `orders.product_code → products.sku`, `returns.order_ref → orders.order_id`, `customer_360.customer_id → customers.customerid`) are found from the values alone, because no pair of names matches.

## Catalog

The catalog is what the model is told about a dataset. It is built once per upload:

- **SQL profiling, during the load:** types, nulls, distinct counts, ranges, exact categorical values, keys, joins and indexes.
- **One LLM call per table:** a one-line description of each column, plus groups of easily confused columns (e.g. `gross_amount` / `net_amount`, `order_date` / `ship_date`, `status` / `status_2`). For the sample workbook this was 5 calls and 17,279 tokens in total, paid once.

```bash
cd backend
python -m catalog describe ../data/tabletalk_sample_ds_1_catalog.json   # add descriptions
python -m catalog index ../data/tabletalk_sample_ds_1_catalog.json      # print the compact index
```

At question time the model never gets the whole catalog. It gets a compact index (tables, columns with one-line descriptions, joins, ambiguity flags), and then full details only for the columns picked for this question. Sizes for the sample workbook (o200k tokenizer, estimates):

| What | Tokens |
|---|---|
| Whole catalog as JSON (the dump-everything approach) | 16,496 |
| Compact index, sent every question | 1,833 |
| Column details for "revenue by customer city" (6 columns) | 391 |
