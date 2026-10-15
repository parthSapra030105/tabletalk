"""
Turning an uploaded file into a ready dataset, in a background thread.

    loading     ingest every sheet into a new schema and build the catalog (one transaction)
    describing  LLM column descriptions; if this fails the dataset is still usable
    ready / failed

Progress is written to the Dataset row, which the UI polls. A thread doesn't survive a
server restart; RUNNING lets the views notice a dataset whose job is gone and mark it
failed instead of leaving it "loading" forever. A task queue would remove that limit.
"""

import dataclasses
import logging
import threading
import time
import zipfile

import psycopg
from django.db import close_old_connections

from catalog.describe import describe_catalog
from ingest.postgres import NoUsableSheet, load_workbook

from .models import Dataset

log = logging.getLogger("api")
RUNNING = set()                  # ids of datasets whose job is alive in this process


def start(dataset_id):
    RUNNING.add(dataset_id)
    threading.Thread(target=run, args=(dataset_id,), daemon=True).start()


def run(dataset_id):
    try:
        _run(dataset_id)
    finally:
        RUNNING.discard(dataset_id)
        close_old_connections()


def _run(dataset_id):
    ds = Dataset.objects.get(pk=dataset_id)
    timings = {}
    _update(ds, status=Dataset.Status.LOADING)

    last_write = 0.0

    def progress(sheet, rows, total):
        nonlocal last_write
        if time.monotonic() - last_write > 0.5:
            last_write = time.monotonic()
            Dataset.objects.filter(pk=ds.pk).update(progress={"sheet": sheet, "rows": rows, "total": total})

    start = time.perf_counter()
    try:
        schema, reports, catalog = load_workbook(ds.file_path, progress=progress)
    except Exception as exc:
        log.exception("ingest failed for dataset %s", ds.pk)
        _update(ds, status=Dataset.Status.FAILED, error=friendly_error(exc))
        return
    timings["load_seconds"] = round(time.perf_counter() - start, 1)
    timings["catalog"] = catalog.pop("timings", {})
    _update(ds, schema_name=schema, report=[dataclasses.asdict(r) for r in reports], catalog=catalog,
            timings=timings, progress={}, status=Dataset.Status.DESCRIBING)

    start = time.perf_counter()
    try:
        describe_catalog(catalog)
    except Exception:               # descriptions improve answers but aren't required for them
        log.exception("descriptions failed for dataset %s", ds.pk)
    timings["describe_seconds"] = round(time.perf_counter() - start, 1)
    _update(ds, catalog=catalog, timings=timings, status=Dataset.Status.READY)


def _update(ds, **fields):
    for k, v in fields.items():
        setattr(ds, k, v)
    ds.save(update_fields=[*fields, "updated_at"])


def friendly_error(exc):
    if isinstance(exc, zipfile.BadZipFile):
        return "This file isn't a valid .xlsx workbook (it may be corrupted, password-protected, or an old .xls file)."
    if isinstance(exc, NoUsableSheet):
        return f"No sheet with a header row and data was found ({exc})."
    if isinstance(exc, psycopg.Error):
        return "The database rejected the load; nothing was saved. Details are in the server log."
    return f"The file couldn't be loaded ({type(exc).__name__}); nothing was saved."
