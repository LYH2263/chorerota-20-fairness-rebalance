"""Member load projection: GET /api/weeks/{week_id}/loads.

Read-only and NOT status-gated — loads are viewable for draft/sealed weeks.
"""

from fastapi import APIRouter, HTTPException

from app.db import connect
from app.engines.rebalance import load_entries, load_range, member_loads
from app.modules.board_io import eligible_members, get_week, task_index, week_slots

router = APIRouter()


@router.get("/api/weeks/{week_id}/loads")
def week_loads(week_id: int):
    c = connect()
    week = get_week(c, week_id)
    if week is None:
        c.close()
        raise HTTPException(404, "week_not_found")
    members = eligible_members(c)
    slots = week_slots(c, week_id)
    weights = {tid: t["weight"] for tid, t in task_index(c).items()}
    c.close()

    eligible_ids = [m["id"] for m in members]
    names = {m["id"]: m["name"] for m in members}
    return {
        "week_id": week_id,
        "range": load_range(member_loads(slots, eligible_ids, weights)),
        "loads": load_entries(slots, eligible_ids, weights, names),
    }
