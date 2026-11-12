"""Measurement helpers for your error log: word error rate, number accuracy, item precision/recall."""
from __future__ import annotations

import re
from collections import Counter

from .schemas import Session
from .trust import norm


def wer(ref: str, hyp: str) -> dict:
    r, h = norm(ref).split(), norm(hyp).split()
    d = [[0] * (len(h) + 1) for _ in range(len(r) + 1)]
    for i in range(len(r) + 1):
        d[i][0] = i
    for j in range(len(h) + 1):
        d[0][j] = j
    for i in range(1, len(r) + 1):
        for j in range(1, len(h) + 1):
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (r[i - 1] != h[j - 1]))
    i, j, sub, dele, ins = len(r), len(h), 0, 0, 0
    while i > 0 or j > 0:
        if i > 0 and j > 0 and d[i][j] == d[i - 1][j - 1] + (r[i - 1] != h[j - 1]):
            sub += r[i - 1] != h[j - 1]
            i, j = i - 1, j - 1
        elif i > 0 and d[i][j] == d[i - 1][j] + 1:
            dele += 1
            i -= 1
        else:
            ins += 1
            j -= 1
    return {"wer": (sub + dele + ins) / max(len(r), 1), "substitutions": sub, "deletions": dele,
            "insertions": ins, "ref_words": len(r)}


def number_recall(ref: str, hyp: str) -> dict:
    """Share of digit-numbers in the reference that the machine got exactly right (digits only)."""
    rn = Counter(re.findall(r"\d[\d,\.]*", ref))
    hn = Counter(re.findall(r"\d[\d,\.]*", hyp))
    total = sum(rn.values())
    hit = sum(min(c, hn[k]) for k, c in rn.items())
    return {"numbers_in_reference": total, "numbers_correct": hit, "recall": (hit / total) if total else None}


def item_scores(s: Session, gold: dict[str, list[list[str]]]) -> dict:
    """gold = {"decision": [["L005"]], "action": [["L006"]], "open_issue": [["L007","L008"]]}.
    An item matches a gold entry when their cited line IDs overlap. Only MACHINE items are scored;
    human-added items are the machine's misses."""
    out = {}
    for kind in ("decision", "action", "open_issue"):
        machine = [set(e.line_id for e in i.evidence) for i in s.items if i.kind == kind and i.origin == "machine"]
        g = [set(x) for x in gold.get(kind, [])]
        tp_items = sum(1 for m in machine if any(m & x for x in g))
        tp_gold = sum(1 for x in g if any(m & x for m in machine))
        out[kind] = {
            "precision": (tp_items / len(machine)) if machine else None,
            "recall": (tp_gold / len(g)) if g else None,
            "machine_items": len(machine), "gold_items": len(g),
        }
    return out
