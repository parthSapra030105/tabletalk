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

from dataclasses import dataclass, field
from typing import Annotated, Literal, TypedDict

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
    """Read-only inputs for a run; not part of the checkpointed state."""
    catalog: dict
    glossary: dict = field(default_factory=dict)  # term -> meaning, for this dataset


# Reset at the start of every turn, so nothing from the previous question leaks into this one.
TURN_DEFAULTS = {"route": None, "route_reason": None, "alternative": "", "selection": {}, "assumptions": [], "sql": None,
                 "explanation": None, "error": None, "attempts": 0, "result": None, "blocks": [], "usage": RESET}
