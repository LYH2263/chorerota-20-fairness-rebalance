"""Rebalance confirm: POST /api/weeks/{week_id}/rebalance/confirm.

Stateless: the body must carry the exact canonical plan recomputed from the
current board. Any mismatch (board changed, tampered or reordered swaps) fails
with plan_stale and leaves assignments untouched. When no improving swap
exists, confirmation always fails with no_improving_swap.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db import connect
from app.engines.rebalance import plan_rebalance, simulate_swaps
from app.modules.board_io import (
    eligible_members,
    gate_balanceable,
    get_week,
    task_index,
    week_slots,
)

router = APIRouter()


class RefCell(BaseModel):
    day: int
    task_id: int


class PlannedSwap(BaseModel):
    a: RefCell
    b: RefCell


class ConfirmBody(BaseModel):
    swaps: list[PlannedSwap] = []
    fingerprint_before: str | None = None


@router.post("/api/weeks/{week_id}/rebalance/confirm")
def rebalance_confirm(week_id: int, body: ConfirmBody = ConfirmBody()):
    c = connect()
    week = get_week(c, week_id)
    slots = week_slots(c, week_id) if week is not None else []
    gate_balanceable(week, slots)
    members = eligible_members(c)
    tasks = task_index(c)

    eligible_ids = [m["id"] for m in members]
    names = {m["id"]: m["name"] for m in members}
    weights = {tid: t["weight"] for tid, t in tasks.items()}
    plan = plan_rebalance(slots, eligible_ids, weights, names)
    if not plan["has_plan"]:
        c.close()
        raise HTTPException(400, "no_improving_swap")

    body_tuples = [(s.a.day, s.a.task_id, s.b.day, s.b.task_id) for s in body.swaps]
    canon_tuples = [(st["a_day"], st["a_task"], st["b_day"], st["b_task"])
                    for st in plan["swaps"]]
    if body_tuples != canon_tuples:
        c.close()
        raise HTTPException(400, "plan_stale")
    if body.fingerprint_before and body.fingerprint_before != plan["fingerprint_before"]:
        c.close()
        raise HTTPException(400, "plan_stale")

    try:
        final = simulate_swaps(slots, plan["swaps"])
    except ValueError:
        c.close()
        raise HTTPException(400, "plan_stale")

    try:
        c.execute("BEGIN IMMEDIATE")
        for s in final:
            cur = c.execute(
                "UPDATE assignments SET member_id=? WHERE week_id=? AND day=? AND task_id=?",
                (s["member_id"], week_id, s["day"], s["task_id"]))
            if cur.rowcount != 1:
                raise RuntimeError("cell_missing")
        c.commit()
    except Exception:
        c.rollback()
        c.close()
        raise HTTPException(409, "board_changed")
    c.close()

    return {
        "ok": True,
        "applied": len(plan["swaps"]),
        "range_after": plan["range_after"],
        "loads_after": plan["loads_after"],
        "fingerprint_before": plan["fingerprint_before"],
        "fingerprint_after": plan["fingerprint_after"],
    }
