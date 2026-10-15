"""
Score the system on questions whose true answers are known.

    python manage.py eval                  # the newest ready sample dataset
    python manage.py eval --dataset 2

The generator writes <workbook>_answer_key.json beside every sample workbook, with figures
computed from the clean data before any mess was added. Each question here is asked through
the same code path as the chat endpoint, in its own thread so earlier answers can't help.
Grading re-runs the SQL that actually ran (read-only) and compares its result with the key:
the numbers the UI shows are filled from that same result, so this grades what a user sees.
Writes docs/eval-report.md.
"""

import datetime as dt
import decimal
import json
import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from agent.tools import run_query
from api import chat
from api.models import Dataset, Thread

CR = 1e7
TOLERANCE = 0.001          # 0.1%: the key rounds crore figures to 4 decimals


def _numbers(rows):
    # Postgres numeric arrives as Decimal; bool is an int subclass and isn't a figure.
    return [v for row in rows for v in row if isinstance(v, (int, float, decimal.Decimal)) and not isinstance(v, bool)]


def _close(a, b):
    return abs(float(a) - float(b)) <= max(abs(float(b)) * TOLERANCE, 0.5)


# Graders take the result (columns, rows) and the answer key, and return (passed, expected-as-text).
def one_number(path, scale=1.0):
    def grade(result, key):
        want = _dig(key, path) * scale
        return any(_close(v, want) for v in _numbers(result.rows)), f"{want:,.0f}"
    return grade


def labelled_numbers(path, scale=CR):
    """Every label (e.g. a region) appears in a row together with its value."""
    def grade(result, key):
        want = {k: v * scale for k, v in _dig(key, path).items()}
        ok = all(any(label in [str(c) for c in row] and any(_close(v, value) for v in _numbers([row])) for row in result.rows)
                 for label, value in want.items())
        return ok, ", ".join(f"{k} {v:,.0f}" for k, v in want.items())
    return grade


def ranking(path, top=5):
    def grade(result, key):
        want = list(_dig(key, path))[:top]
        got = [next((str(c) for c in row if isinstance(c, str)), None) for row in result.rows[:top]]
        return got == want, " > ".join(want)
    return grade


def top_label(path):
    def grade(result, key):
        want = next(iter(_dig(key, path)))
        return bool(result.rows) and want in [str(c) for c in result.rows[0]], want
    return grade


def top_order(path):
    def grade(result, key):
        want = _dig(key, path)[0][0]
        return bool(result.rows) and want in [str(c) for c in result.rows[0]], want
    return grade


def empty(result, key):
    return (not result.rows or all(v is None for row in result.rows for v in row)), "no rows"


def _dig(key, path):
    for part in path.split("."):
        key = key[part]
    return key


QUESTIONS = [
    ("lookup", "What were total sales in March 2025, by region?", labelled_numbers("net_revenue_mar_2025_by_region_cr")),
    ("total", "What was our net revenue in FY26 (April 2025 to March 2026)?", one_number("gross_vs_net_fy26_cr.net", CR)),
    ("gross vs net", "What was gross revenue before discounts in FY26 (April 2025 to March 2026)?", one_number("gross_vs_net_fy26_cr.gross", CR)),
    ("date column", "How many orders did we ship between July and September 2025?", one_number("orders_shipped_q2.fy26_q2_jul_sep_2025_by_ship_date")),
    ("join", "Which 5 customer cities bring in the most revenue?", ranking("net_revenue_by_customer_city_top5_cr")),
    ("planted story", "How many orders did the East region get in August 2025?", one_number("east_orders_jun_oct_2025.2025-08")),
    # Says "percentage" on purpose: "grew the most" alone is fairly read as the largest rupee increase too.
    ("trend", "Which product category had the highest percentage growth in net revenue from September 2025 to March 2026, comparing the two months?",
     top_label("category_net_growth_pct_sep25_to_mar26")),
    ("outlier", "What is the single biggest order by gross amount?", top_order("top_3_orders_gross")),
    ("count", "How many orders were cancelled in total?", one_number("status_counts.Cancelled")),
    ("honest empty", "What was revenue in 2031?", empty),
]


class Command(BaseCommand):
    help = "Ask questions with known answers and score the results."

    def add_arguments(self, parser):
        parser.add_argument("--dataset", type=int, help="dataset to evaluate (default: newest ready sample)")

    def handle(self, *args, dataset=None, **options):
        qs = Dataset.objects.filter(status=Dataset.Status.READY)
        ds = qs.filter(pk=dataset).first() if dataset else qs.filter(is_sample=True).order_by("-created_at").first()
        if ds is None:
            raise CommandError("No ready dataset. Run load_sample first.")
        key_path = Path(ds.file_path).with_name(Path(ds.file_path).stem + "_answer_key.json")
        if not key_path.exists():
            raise CommandError(f"No answer key at {key_path}; the eval needs a generated sample workbook.")
        key = json.loads(key_path.read_text(encoding="utf-8"))
        catalog = {**ds.catalog, "schema": ds.schema_name}

        results = []
        for kind, question, grade in QUESTIONS:
            thread = Thread.objects.create(dataset=ds, title=f"[eval] {question}")
            start = time.perf_counter()
            m = chat.ask(thread, question)
            seconds = round(time.perf_counter() - start, 1)
            if m.sql:
                ok, expected = grade(run_query(m.sql, catalog), key)
            else:
                ok, expected = False, "a query"
            results.append((kind, question, expected, m, ok, seconds))
            self.stdout.write(f"{'PASS' if ok else 'FAIL'}  {kind:<13} {question}")
            chat.checkpointer().delete_thread(str(thread.id))
            thread.delete()
        chat.shutdown()

        score = sum(r[4] for r in results)
        path = self.write_report(ds, results, score)
        self.stdout.write(self.style.SUCCESS(f"{score}/{len(results)} correct. Report: {path}"))

    def write_report(self, ds, results, score):
        tokens = sum(r[3].total_tokens for r in results)
        lines = [
            "# Eval report",
            "",
            f"Generated by `python manage.py eval` on {dt.datetime.now():%d %b %Y %H:%M}, against **{ds.name}**.",
            "Expected answers come from the generator's answer key (computed from the clean data before the mess",
            "was added). Each answer is graded by re-running the SQL that ran and comparing its result with the key.",
            "",
            f"**Score: {score}/{len(results)}** · {tokens:,} tokens in total · "
            f"{sum(r[5] for r in results):.0f}s",
            "",
            "| Kind | Question | Expected | Result | Tokens | Seconds |",
            "|---|---|---|---|---|---|",
        ]
        for kind, q, expected, m, ok, secs in results:
            lines.append(f"| {kind} | {q} | {expected} | {'PASS' if ok else '**FAIL**'} | {m.total_tokens:,} | {secs} |")
        lines += ["", "## Queries", ""]
        for kind, q, _, m, ok, _ in results:
            answer = next((b["content"] for b in m.blocks if b["type"] == "text"), "")
            lines += [f"### {q}", "", f"{'PASS' if ok else 'FAIL'} · {answer}", "", "```sql", m.sql or "-- no query ran", "```", ""]
        path = settings.REPO_DIR / "docs" / "eval-report.md"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path
