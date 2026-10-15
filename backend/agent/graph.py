"""
The Tabletalk graph.

    START -> start -> router --write------> refuse --------------------------------\
                             --off_topic--> redirect -------------------------------|
                             --about_file-> describe -------------------------------|
                             --vague------> clarify --------------------------------|
                             --define-----> remember -------------------------------+--> finish -> END
                             --data-------> schema --can't answer--> explain_missing|
                                              |                                     |
                                              v                                     |
                            +--------------> sql ---> validate ---> run ---> answer ------|
                            |                 |          |           |
                            +--- retry <------+----------+-----------+   (an error, at most 2 retries)
                                              |
                                           give_up -----------------------------------/

The boxes that touch the database (validate, run) contain no LLM. A write request is
refused before any SQL exists.
"""

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from . import data_nodes as d
from . import nodes as n
from .answer import answer
from .state import Context, State


def build(checkpointer=None):
    g = StateGraph(State, context_schema=Context)
    for name, fn in [("start", n.start), ("router", n.router), ("refuse", n.refuse), ("redirect", n.redirect),
                     ("describe", n.describe), ("clarify", n.clarify), ("remember", d.remember),
                     ("schema", d.schema), ("explain_missing", d.explain_missing), ("sql", d.sql),
                     ("validate", d.validate), ("run", d.run), ("give_up", d.give_up),
                     ("answer", answer), ("finish", n.finish)]:
        g.add_node(name, fn)

    g.add_edge(START, "start")
    g.add_edge("start", "router")
    g.add_conditional_edges("router", n.after_router, {
        "write": "refuse", "off_topic": "redirect", "about_file": "describe",
        "vague": "clarify", "define": "remember", "data": "schema",
    })
    g.add_conditional_edges("schema", d.after_schema, {"answerable": "sql", "missing": "explain_missing"})
    # The retry loop: any failure goes back to sql with the error, at most MAX_RETRIES times.
    g.add_conditional_edges("sql", d.after_sql, {"query": "validate", "retry": "sql", "out_of_retries": "give_up"})
    g.add_conditional_edges("validate", d.after_validate, {"valid": "run", "retry": "sql", "out_of_retries": "give_up"})
    g.add_conditional_edges("run", d.after_run, {"rows": "answer", "retry": "sql", "out_of_retries": "give_up"})
    for terminal in ["refuse", "redirect", "describe", "clarify", "remember", "explain_missing",
                     "give_up", "answer"]:
        g.add_edge(terminal, "finish")
    g.add_edge("finish", END)
    return g.compile(checkpointer=checkpointer or InMemorySaver())
