"""Shared read-only data access + week gating for the rebalance modules."""

from fastapi import HTTPException


def get_week(c, week_id: int):
    return c.execute("SELECT * FROM weeks WHERE id=?", (week_id,)).fetchone()


def eligible_members(c) -> list[dict]:
    """Active + clean members, ordered by id (same filter as generate)."""
    return [dict(r) for r in c.execute(
        "SELECT id,name FROM members WHERE active=1 AND data_quality='clean' ORDER BY id")]


def member_names(c) -> dict:
    return {r["id"]: r["name"] for r in c.execute("SELECT id,name FROM members")}


def task_index(c) -> dict:
    return {r["id"]: {"title": r["title"], "weight": r["weight"]}
            for r in c.execute("SELECT id,title,weight FROM tasks")}


def week_slots(c, week_id: int) -> list[dict]:
    rows = c.execute(
        "SELECT day,task_id,member_id FROM assignments WHERE week_id=? ORDER BY day,task_id",
        (week_id,))
    return [dict(r) for r in rows]


def gate_balanceable(week, slots: list[dict]):
    """Raise the canonical HTTP error unless the week may be rebalanced.

    Order matters: missing -> sealed -> not-ready (draft or empty board).
    """
    if week is None:
        raise HTTPException(404, "week_not_found")
    if week["status"] == "sealed":
        raise HTTPException(400, "week_sealed")
    if week["status"] != "ready" or not slots:
        raise HTTPException(400, "week_not_ready")


def enrich_swap_step(step: dict, idx: int, names: dict, tasks: dict) -> dict:
    """UI/API payload for one planned step; occupants are pre-step occupants."""
    def cell(day, task_id, member_id):
        t = tasks.get(task_id, {})
        return {
            "day": day,
            "task_id": task_id,
            "task_title": t.get("title", "?"),
            "weight": t.get("weight", 0),
            "member_id": member_id,
            "member_name": names.get(member_id, "?"),
        }
    return {
        "step": idx + 1,
        "a": cell(step["a_day"], step["a_task"], step["a_member"]),
        "b": cell(step["b_day"], step["b_task"], step["b_member"]),
        "range_before": step["range_before"],
        "range_after": step["range_after"],
    }
