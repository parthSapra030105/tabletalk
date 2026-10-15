"""
UI blocks (the JSON the frontend draws) and the number audit.

Every block is built here, by code. The model chooses what to show and writes words;
it never writes the numbers inside a block.

audit_text() is the last line of defence for numbers in prose: any sentence that
contains a number not found in the facts the model was given is removed.
"""

import re

_NUMBER = re.compile(r"(?<![\w.])-?\d[\d,]*(?:\.\d+)?")
_ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def _is_calendar(n):
    """Day numbers and years ('1 April 2024', 'FY 2025') are not quantities the audit needs to trace."""
    return n.is_integer() and (0 <= n <= 31 or 1900 <= n <= 2100)


def text(content):
    return {"type": "text", "content": content}


def notice(content):
    return {"type": "notice", "content": content}


def table(columns, rows):
    return {"type": "table", "columns": list(columns), "rows": [list(r) for r in rows]}


def suggestions(options):
    return {"type": "suggestions", "options": [o for o in options if o][:4]}


def numbers_in(s):
    """'600,000 rows and 4.5%' -> {600000.0, 4.5}"""
    found = set()
    s = _ISO_DATE.sub(lambda m: m.group(0).replace("-", " "), s or "")
    for m in _NUMBER.findall(s):
        try:
            found.add(float(m.replace(",", "")))
        except ValueError:
            pass
    return found


def audit_text(content, allowed):
    """Drop sentences that contain a number not in `allowed`. Returns (clean text, dropped sentences)."""
    kept, dropped = [], []
    for sentence in _SENTENCE_END.split(content.strip()):
        unexplained = {n for n in numbers_in(sentence) - allowed if not _is_calendar(n)}
        (dropped if unexplained else kept).append(sentence)
    return " ".join(kept), dropped
