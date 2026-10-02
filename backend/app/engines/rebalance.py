"""Greedy local cell-swap load rebalancing (pure functions, no DB).

One "pass" repeatedly applies the single pairwise swap that most reduces the
weighted-load range (max - min over eligible members), with a deterministic
lexicographic tie-break, and stops at the pairwise local optimum. Every
recorded step strictly decreases the range.
"""

import hashlib

from app.engines.rota import apply_swap


def canonical_slots(slots: list[dict]) -> list[dict]:
    """Shallow-copy slots in canonical (day, task_id) order."""
    return sorted((dict(s) for s in slots), key=lambda s: (s["day"], s["task_id"]))


def member_loads(slots: list[dict], eligible_ids: list[int], weights: dict) -> dict:
    """{member_id: {"load": int, "cells": int}} for every eligible member.

    Cells held by non-eligible members are ignored. A task missing from the
    weights map contributes 0 (generated boards only contain clean, weight>0
    tasks, so this is purely defensive).
    """
    loads = {mid: {"load": 0, "cells": 0} for mid in eligible_ids}
    for s in slots:
        mid = s["member_id"]
        if mid in loads:
            loads[mid]["load"] += int(weights.get(s["task_id"], 0))
            loads[mid]["cells"] += 1
    return loads


def load_range(load_map: dict) -> int:
    """max - min across eligible members; 0 when there are fewer than two."""
    if not load_map:
        return 0
    vals = [v["load"] for v in load_map.values()]
    return max(vals) - min(vals)


def load_entries(slots: list[dict], eligible_ids: list[int], weights: dict,
                 names: dict) -> list[dict]:
    """Per-member load rows sorted by member_id (the shared projection shape)."""
    loads = member_loads(slots, eligible_ids, weights)
    return [
        {
            "member_id": mid,
            "member_name": names.get(mid, "?"),
            "load": loads[mid]["load"],
            "cells": loads[mid]["cells"],
        }
        for mid in sorted(eligible_ids)
    ]


def board_fingerprint(slots: list[dict]) -> str:
    """Deterministic digest of the (day, task_id) -> member_id board."""
    rows = [f"{s['day']},{s['task_id']},{s['member_id']}" for s in canonical_slots(slots)]
    return "sha256:" + hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest()


def simulate_swaps(slots: list[dict], steps: list[dict]) -> list[dict]:
    """Fold the recorded swaps over a board; raises ValueError on illegality."""
    out = canonical_slots(slots)
    for st in steps:
        out = apply_swap(out, st["a_day"], st["a_task"], st["b_day"], st["b_task"])
    return out


def plan_rebalance(slots: list[dict], eligible_ids: list[int], weights: dict,
                   names: dict) -> dict:
    """Greedily swap eligible-owned cell pairs while the range strictly drops.

    Strategy (locked): best-improvement pairwise hill climbing. Each round all
    cell pairs are visited in lexicographic (a_day, a_task, b_day, b_task)
    order; both occupants must be distinct eligible members. The swap with the
    largest range decrease wins; ties keep the first (lexicographically
    smallest) pair. Stops when no pair strictly decreases the range.
    """
    eligible = set(eligible_ids)
    current = canonical_slots(slots)
    before_map = member_loads(current, eligible_ids, weights)
    cur_range = load_range(before_map)
    range_before = cur_range
    fp_before = board_fingerprint(current)

    steps = []
    n = len(current)
    while True:
        best = None  # (decrease, key, after_slots, a_member, b_member)
        for i in range(n):
            a = current[i]
            if a["member_id"] not in eligible:
                continue
            for j in range(i + 1, n):
                b = current[j]
                if b["member_id"] not in eligible:
                    continue
                if a["member_id"] == b["member_id"]:
                    continue
                key = (a["day"], a["task_id"], b["day"], b["task_id"])
                sim = apply_swap(current, a["day"], a["task_id"], b["day"], b["task_id"])
                new_range = load_range(member_loads(sim, eligible_ids, weights))
                dec = cur_range - new_range
                if dec > 0 and (best is None or dec > best[0]):
                    best = (dec, key, sim, a["member_id"], b["member_id"], new_range)
        if best is None:
            break
        dec, key, sim, ma, mb, new_range = best
        steps.append({
            "a_day": key[0], "a_task": key[1], "b_day": key[2], "b_task": key[3],
            "a_member": ma, "b_member": mb,
            "range_before": cur_range, "range_after": new_range,
        })
        current, cur_range = sim, new_range

    return {
        "has_plan": bool(steps),
        "swaps": steps,
        "range_before": range_before,
        "range_after": cur_range,
        "loads_before": load_entries(canonical_slots(slots), eligible_ids, weights, names),
        "loads_after": load_entries(current, eligible_ids, weights, names),
        "fingerprint_before": fp_before,
        "fingerprint_after": board_fingerprint(current),
    }
