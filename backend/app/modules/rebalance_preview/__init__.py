"""Rebalance preview: POST /api/weeks/{week_id}/rebalance/preview.

Read-only: computes the canonical greedy plan from the current board and
returns it with before/after loads and range. Assignments are never written.
"""

from fastapi import APIRouter

from app.db import connect
from app.engines.rebalance import plan_rebalance
from app.modules.board_io import (
    eligible_members,
    enrich_swap_step,
    gate_balanceable,
    get_week,
    task_index,
    week_slots,
)

router = APIRouter()


@router.post("/api/weeks/{week_id}/rebalance/preview")
def rebalance_preview(week_id: int):
    c = connect()
    week = get_week(c, week_id)
    slots = week_slots(c, week_id) if week is not None else []
    gate_balanceable(week, slots)
    members = eligible_members(c)
    tasks = task_index(c)
    c.close()

    eligible_ids = [m["id"] for m in members]
    names = {m["id"]: m["name"] for m in members}
    weights = {tid: t["weight"] for tid, t in tasks.items()}
    plan = plan_rebalance(slots, eligible_ids, weights, names)

    return {
        "week_id": week_id,
        "has_plan": plan["has_plan"],
        "range_before": plan["range_before"],
        "range_after": plan["range_after"],
        "loads_before": plan["loads_before"],
        "loads_after": plan["loads_after"],
        "fingerprint_before": plan["fingerprint_before"],
        "fingerprint_after": plan["fingerprint_after"],
        "swaps": [
            enrich_swap_step(st, i, names, tasks)
            for i, st in enumerate(plan["swaps"])
        ],
    }
