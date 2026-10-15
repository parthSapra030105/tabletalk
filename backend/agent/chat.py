"""
Talk to the graph from the terminal.

    cd backend
    python -m agent.chat ../data/tabletalk_sample_ds_1_catalog.json                        # interactive
    python -m agent.chat ../data/tabletalk_sample_ds_1_catalog.json -q "first" -q "second"  # scripted turns
    python -m agent.chat ../data/tabletalk_sample_ds_1_catalog.json --mermaid               # print the graph

All turns of one run share a thread, so follow-ups see earlier turns.
"""

import argparse
import json
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv

from .graph import build
from .state import Context


def show(state):
    print(f"  route: {state.get('route')}  ({state.get('route_reason')})")
    if state.get("attempts"):
        print(f"  failed attempts: {state['attempts']} (last error: {state.get('error')})")
    for b in state.get("blocks", []):
        if b["type"] in ("text", "notice"):
            print(f"  [{b['type']}] {b['content']}")
        elif b["type"] == "sql":
            print(f"  [sql] {b['query']}")
        elif b["type"] == "metric":
            print(f"  [metric] {b['label']}: {b['display']}")
        elif b["type"].endswith("_chart"):
            preview = ", ".join(f"{r[b['x']]}{'/' + str(r[b['series']]) if b.get('series') else ''}={r[b['y']]}"
                                for r in b["rows"][:5])
            print(f"  [{b['type']}] x={b['x']} y={b['y']} series={b.get('series')} ({len(b['rows'])} points) {preview}…")
        elif b["type"] == "suggestions":
            print(f"  [suggestions] {' | '.join(b['options'])}")
        elif b["type"] == "table":
            print(f"  [table] {b['columns']}")
            for r in b["rows"][:8]:
                print(f"           {r}")
            if len(b["rows"]) > 8:
                print(f"           … {len(b['rows']) - 8} more rows")
        else:
            print(f"  [{b['type']}] {json.dumps(b, ensure_ascii=False, default=str)[:200]}")
    usage = state.get("usage", [])
    if usage:
        calls = ", ".join(f"{u['purpose']} {u['total_tokens']}" for u in usage)
        print(f"  tokens this turn: {sum(u['total_tokens'] for u in usage)} ({calls}); "
              f"{sum(u['seconds'] for u in usage):.1f}s in the model")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    parser = argparse.ArgumentParser()
    parser.add_argument("catalog", nargs="?", help="catalog JSON written by `python -m ingest ... --load`")
    parser.add_argument("-q", "--question", action="append", help="ask this and exit (repeatable)")
    parser.add_argument("--mermaid", action="store_true", help="print the graph as a Mermaid diagram")
    args = parser.parse_args()

    graph = build()
    if args.mermaid:
        print(graph.get_graph().draw_mermaid())
        return
    if not args.catalog:
        parser.error("a catalog file is needed to chat")
    glossary_path = Path(args.catalog).with_name(Path(args.catalog).stem + "_glossary.json")
    glossary = json.loads(glossary_path.read_text(encoding="utf-8")) if glossary_path.exists() else {}
    context = Context(catalog=json.loads(Path(args.catalog).read_text(encoding="utf-8")), glossary=glossary,
                      save_glossary=lambda g: glossary_path.write_text(json.dumps(g, indent=2), encoding="utf-8"))
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}

    questions = args.question or iter(lambda: input("\n> ").strip(), "")
    for q in questions:
        print(f"\n> {q}" if args.question else "")
        show(graph.invoke({"question": q}, config, context=context))


if __name__ == "__main__":
    main()
