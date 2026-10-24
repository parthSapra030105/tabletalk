"""
The JSON API. Plain Django views; there is no login, so there are no sessions or CSRF tokens
to protect (CsrfViewMiddleware isn't installed).
"""

import datetime as dt
import json
import logging
import uuid
import zipfile
from functools import wraps
from pathlib import Path

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from psycopg import sql

from . import chat, jobs
from .models import Dataset, GlossaryEntry, Thread

log = logging.getLogger("api")
MAX_QUESTION_CHARS = 1000
IN_PROGRESS = {Dataset.Status.QUEUED, Dataset.Status.LOADING, Dataset.Status.DESCRIBING}


def respond(data, status=200):
    return JsonResponse(data, status=status, encoder=DjangoJSONEncoder, safe=False)


def error(message, status=400):
    return respond({"error": message}, status)


def json_body(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        try:
            request.json = json.loads(request.body or b"{}")
        except json.JSONDecodeError:
            return error("The request body must be JSON.")
        return view(request, *args, **kwargs)
    return wrapper


# --- datasets ---------------------------------------------------------------------

def _mark_if_interrupted(ds):
    """A job lost to a server restart would otherwise look 'loading' forever."""
    stale = timezone.now() - ds.updated_at > dt.timedelta(minutes=10)
    if ds.status in IN_PROGRESS and ds.pk not in jobs.RUNNING and stale:
        ds.status, ds.error = Dataset.Status.FAILED, "Loading was interrupted (the server restarted). Please upload again."
        ds.save(update_fields=["status", "error", "updated_at"])


def dataset_summary(ds):
    tables = ds.catalog.get("tables", [])
    return {"id": ds.pk, "name": ds.name, "status": ds.status, "progress": ds.progress, "error": ds.error,
            "is_sample": ds.is_sample, "created_at": ds.created_at, "file_size": ds.file_size,
            "tables": len(tables), "rows": sum(t["row_count"] for t in tables), "threads": ds.threads.count()}


def dataset_detail(ds):
    out = dataset_summary(ds)
    out["timings"] = ds.timings
    out["sheets"] = [{
        "sheet": r["sheet"], "table": r["table"], "status": r["status"], "reason": r["reason"],
        "header_row": r["header_row"], "rows_loaded": r["rows_loaded"], "skipped_rows": r["skipped_rows"],
        "range": r.get("range"), "title": r.get("title"), "notes": r.get("notes", []), "hidden": r.get("hidden", False),
        "columns": [{"name": c["name"], "original": c["original"], "type": c["type"], "nulls": c["nulls"],
                     "coercion_failures": c["coercion_failures"], "failure_examples": c["failure_examples"],
                     "note": c["note"]} for c in r["columns"]],
    } for r in ds.report]
    out["catalog"] = {
        "tables": [{"name": t["name"], "rows": t["row_count"], "description": t.get("description", ""),
                    "ambiguities": t.get("ambiguities", []),
                    "columns": [{"name": c["name"], "original": c["original"], "type": c["type"],
                                 "description": c.get("description", "")} for c in t["columns"]]}
                   for t in ds.catalog.get("tables", [])],
        "joins": ds.catalog.get("joins", []),
    }
    return out


@require_http_methods(["GET", "POST"])
def datasets(request):
    if request.method == "GET":
        items = list(Dataset.objects.all())
        for ds in items:
            _mark_if_interrupted(ds)
        return respond([dataset_summary(ds) for ds in items])

    upload = request.FILES.get("file")
    if upload is None:
        return error("Attach an .xlsx file in the 'file' field.")
    if not upload.name.lower().endswith(".xlsx"):
        return error("Only .xlsx workbooks are supported (save older .xls or .csv files as .xlsx first).")
    if upload.size > settings.MAX_UPLOAD_BYTES:
        return error(f"The file is larger than {settings.MAX_UPLOAD_BYTES // (1024 * 1024)} MB.", 413)
    if not zipfile.is_zipfile(upload):
        return error("This file isn't a valid .xlsx workbook (it may be corrupted or password-protected).")
    upload.seek(0)
    with zipfile.ZipFile(upload) as z:
        if "xl/workbook.xml" not in z.namelist():
            return error("This file isn't an Excel workbook.")
    upload.seek(0)

    settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    path = settings.UPLOAD_DIR / f"{uuid.uuid4().hex}.xlsx"
    with open(path, "wb") as f:
        for chunk in upload.chunks():
            f.write(chunk)
    name = (request.POST.get("name") or Path(upload.name).stem)[:255]
    ds = Dataset.objects.create(name=name, file_path=str(path), file_size=upload.size)
    jobs.start(ds.pk)
    return respond(dataset_summary(ds), 202)


@require_http_methods(["GET", "DELETE"])
def dataset(request, dataset_id):
    ds = Dataset.objects.filter(pk=dataset_id).first()
    if ds is None:
        return error("No such dataset.", 404)
    if request.method == "GET":
        _mark_if_interrupted(ds)
        return respond(dataset_detail(ds))

    if ds.status in IN_PROGRESS and ds.pk in jobs.RUNNING:
        return error("This dataset is still loading; delete it once it has finished.", 409)
    if ds.schema_name:
        with connection.cursor() as cur:
            cur.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(ds.schema_name)).as_string(None))
    saver = chat.checkpointer()
    for thread_id in ds.threads.values_list("id", flat=True):
        saver.delete_thread(str(thread_id))
    Path(ds.file_path).unlink(missing_ok=True)
    ds.delete()
    return respond({"deleted": dataset_id})


@require_http_methods(["GET"])
def glossary(request, dataset_id):
    entries = GlossaryEntry.objects.filter(dataset_id=dataset_id).order_by("term")
    return respond([{"term": e.term, "meaning": e.meaning, "columns": e.columns} for e in entries])


@require_http_methods(["DELETE"])
def glossary_entry(request, dataset_id, term):
    deleted, _ = GlossaryEntry.objects.filter(dataset_id=dataset_id, term=term).delete()
    return respond({"deleted": term}) if deleted else error("No such term.", 404)


# --- threads and messages ------------------------------------------------------------

def message_json(m):
    return {"id": m.pk, "question": m.question, "blocks": m.blocks, "route": m.route, "sql": m.sql,
            "total_tokens": m.total_tokens, "seconds": m.seconds, "created_at": m.created_at,
            "usage": m.usage}


@require_http_methods(["GET", "POST"])
def threads(request, dataset_id):
    ds = Dataset.objects.filter(pk=dataset_id).first()
    if ds is None:
        return error("No such dataset.", 404)
    if request.method == "POST":
        if ds.status != Dataset.Status.READY:
            return error("This dataset isn't ready yet.", 409)
        t = Thread.objects.create(dataset=ds)
        return respond({"id": t.id, "title": "", "messages": []}, 201)
    return respond([{"id": t.id, "title": t.title, "updated_at": t.updated_at, "messages": t.messages.count()}
                    for t in ds.threads.all()])


@require_http_methods(["GET", "DELETE"])
def thread(request, thread_id):
    t = Thread.objects.filter(pk=thread_id).first()
    if t is None:
        return error("No such thread.", 404)
    if request.method == "DELETE":
        chat.checkpointer().delete_thread(str(t.id))
        t.delete()
        return respond({"deleted": str(thread_id)})
    return respond({"id": t.id, "title": t.title, "dataset": t.dataset_id,
                    "messages": [message_json(m) for m in t.messages.all()]})


@require_http_methods(["POST"])
@json_body
def messages(request, thread_id):
    t = Thread.objects.select_related("dataset").filter(pk=thread_id).first()
    if t is None:
        return error("No such thread.", 404)
    if t.dataset.status != Dataset.Status.READY:
        return error("This dataset isn't ready yet.", 409)
    question = str(request.json.get("question", "")).strip()
    if not question:
        return error("Ask a question.")
    if len(question) > MAX_QUESTION_CHARS:
        return error(f"Please keep questions under {MAX_QUESTION_CHARS} characters.")
    return respond(message_json(chat.ask(t, question)), 201)
