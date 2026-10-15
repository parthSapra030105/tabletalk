"""
Answering a question in a thread.

The graph is compiled once per process with LangGraph's Postgres checkpointer, so a
thread's state (its last few turns) survives page refreshes and server restarts. Each
question runs the graph with the dataset's catalog and glossary as the run's context and
is saved as a Message: the transcript the UI shows and the per-turn token log.

Whatever goes wrong, the user gets an answer block explaining it, never a 500.
"""

import logging
import os
import threading
import time

import openai
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from agent import blocks
from agent.graph import build
from agent.state import Context

from .models import GlossaryEntry, Message

log = logging.getLogger("api")
_graph = None
_saver = None
_lock = threading.Lock()


def checkpointer():
    global _saver
    if _saver is None:
        from langgraph.checkpoint.postgres import PostgresSaver
        pool = ConnectionPool(os.environ["DATABASE_URL"], max_size=5, open=True,
                              kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row})
        _saver = PostgresSaver(pool)
        _saver.setup()                       # creates the checkpoint tables in `public` if missing
    return _saver


def graph():
    global _graph
    with _lock:
        if _graph is None:
            _graph = build(checkpointer())
    return _graph


def ask(thread, question):
    dataset = thread.dataset
    glossary = {e.term: {"meaning": e.meaning, "columns": e.columns} for e in dataset.glossary.all()}

    def save_glossary(entries):
        for term, entry in entries.items():
            GlossaryEntry.objects.update_or_create(dataset=dataset, term=term,
                                                   defaults={"meaning": entry["meaning"], "columns": entry["columns"]})

    context = Context(catalog=dataset.catalog, glossary=glossary, save_glossary=save_glossary)
    config = {"configurable": {"thread_id": str(thread.id)}}
    start = time.perf_counter()
    state = {}
    try:
        state = graph().invoke({"question": question}, config, context=context)
        answer = state.get("blocks") or [blocks.text("I couldn't produce an answer for that.")]
    except openai.APIError:
        log.exception("LLM unavailable in thread %s", thread.id)
        answer = [blocks.text("The language model is unavailable right now, so I couldn't answer. "
                              "Nothing was changed; please try again in a minute.")]
    except Exception:
        log.exception("graph failed in thread %s", thread.id)
        answer = [blocks.text("Something went wrong while answering. Nothing was changed.")]

    usage = state.get("usage") or []
    ran_sql = (state.get("sql") or "") if state.get("result") else ""     # only a query that actually ran
    message = Message.objects.create(
        thread=thread, question=question, blocks=answer, route=state.get("route") or "", sql=ran_sql, usage=usage,
        total_tokens=sum(u["total_tokens"] for u in usage), seconds=round(time.perf_counter() - start, 1))
    if not thread.title:
        thread.title = question[:200]
    thread.save()
    return message


def shutdown():
    """Close the checkpointer's connection pool (for commands that exit right after using the graph)."""
    if _saver is not None:
        _saver.conn.close()
