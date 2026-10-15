"""
What flows through the graph.

State is per chat thread and is saved by the checkpointer after every node, so
it holds only small things. The catalog is large and doesn't change during a chat,
so it travels in the run's Context instead and is never checkpointed.

Reducers decide how a node's return value is merged into the state:
    usage    appends; the start node resets it, so it always holds this turn's LLM calls
    history  appends a finished turn and keeps only the last MAX_HISTORY
everything else is simply overwritten.
"""

import json
from dataclasses import dataclass, field
from typing import Annotated, Callable, Literal, TypedDict

MAX_HISTORY = 3
RESET = "reset"

Route = Literal["data", "about_file", "write", "off_topic", "define", "vague"]


def usage_reducer(current, update):
    if update == RESET:
        return []
    return (current or []) + update


def history_reducer(current, update):
    return ((current or []) + update)[-MAX_HISTORY:]


class State(TypedDict, total=False):
    # input
    question: str
    # memory across turns
    history: Annotated[list, history_reducer]     # [{question, route, sql, answer}]
    # this turn
    route: Route
    route_reason: str
    alternative: str                              # a read-only question to offer instead of a write
    selection: dict                               # {table: [columns]} picked by the schema node
    assumptions: list
    sql: str | None
    explanation: str | None
    error: str | None
    attempts: int
    result: dict | None
    blocks: list                                  # what the UI draws
    usage: Annotated[list, usage_reducer]         # this turn's LLM calls


@dataclass
class Context:
    """Inputs for a run that are not part of the checkpointed state."""
    catalog: dict
    glossary: dict = field(default_factory=dict)  # term -> {"meaning", "columns"}, for this dataset
    save_glossary: Callable[[dict], None] | None = None   # persists the glossary when a definition is added


# Reset at the start of every turn, so nothing from the previous question leaks into this one.
TURN_DEFAULTS = {"route": None, "route_reason": None, "alternative": "", "selection": {}, "assumptions": [], "sql": None,
                 "explanation": None, "error": None, "attempts": 0, "result": None, "blocks": [], "usage": RESET}


def recent_context(state):
    """What a prompt gets of the conversation: the last few questions and the last SQL that ran.
    Bounded, so the cost of a turn doesn't grow with the length of the chat."""
    history = state.get("history") or []
    last_sql = next((t["sql"] for t in reversed(history) if t.get("sql")), None)
    return json.dumps({"recent_questions": [t["question"] for t in history],
                       "last_sql_that_ran": last_sql}, ensure_ascii=False)
