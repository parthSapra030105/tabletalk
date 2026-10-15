"""
The Tabletalk graph.

    START -> start -> router --write------> refuse ------\
                             --off_topic--> redirect ----|
                             --about_file-> describe ----|
                             --vague------> clarify -----+--> finish -> END
                             --data-------> (part 2) ----|
                             --define-----> (part 2) ----/

Part 1: routing and the branches that never touch the data.
"""

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from . import nodes
from .state import Context, State


def build(checkpointer=None):
    g = StateGraph(State, context_schema=Context)
    g.add_node("start", nodes.start)
    g.add_node("router", nodes.router)
    g.add_node("refuse", nodes.refuse)
    g.add_node("redirect", nodes.redirect)
    g.add_node("describe", nodes.describe)
    g.add_node("clarify", nodes.clarify)
    g.add_node("not_built", nodes.not_built)
    g.add_node("finish", nodes.finish)

    g.add_edge(START, "start")
    g.add_edge("start", "router")
    g.add_conditional_edges("router", nodes.after_router, {
        "write": "refuse",
        "off_topic": "redirect",
        "about_file": "describe",
        "vague": "clarify",
        "data": "not_built",
        "define": "not_built",
    })
    for terminal in ["refuse", "redirect", "describe", "clarify", "not_built"]:
        g.add_edge(terminal, "finish")
    g.add_edge("finish", END)
    return g.compile(checkpointer=checkpointer or InMemorySaver())
