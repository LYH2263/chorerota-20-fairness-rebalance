"""负荷重平衡确认:把预览方案逐步钉到当前格子上,全部校验通过才返回新格子。

校验规则(任一步失败即抛 PlanError,调用方不得落库):
- 方案非空(no_plan);
- 每格的期望归属与当前状态一致,否则方案已过期(stale_plan);
- 改派/对调的目标必须是在岗且干净的成员,不得引入脏成员(dirty_member);
- 应用完整方案后极差必须严格下降(no_improvement)。
"""
from app.engines.rebalance.loads import project_loads, load_range


class PlanError(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _find(slots: list[dict], day, task_id):
    for s in slots:
        if s["day"] == day and s["task_id"] == task_id:
            return s
    return None


def _apply_checked(slots: list[dict], step: dict, member_ids: list[int]) -> list[dict]:
    kind = step.get("kind")
    out = [dict(s) for s in slots]
    if kind == "move":
        t = _find(out, step.get("day"), step.get("task_id"))
        if t is None:
            raise PlanError("slot_missing")
        if t["member_id"] != step.get("from_member_id"):
            raise PlanError("stale_plan")
        if step.get("to_member_id") == step.get("from_member_id"):
            raise PlanError("bad_step")
        if step.get("to_member_id") not in member_ids:
            raise PlanError("dirty_member")
        t["member_id"] = step["to_member_id"]
        return out
    if kind == "swap":
        a = _find(out, step.get("a_day"), step.get("a_task"))
        b = _find(out, step.get("b_day"), step.get("b_task"))
        if a is None or b is None:
            raise PlanError("slot_missing")
        if a["member_id"] != step.get("a_member_id") or b["member_id"] != step.get("b_member_id"):
            raise PlanError("stale_plan")
        if a["member_id"] == b["member_id"]:
            raise PlanError("same_assignee")
        if a["member_id"] not in member_ids or b["member_id"] not in member_ids:
            raise PlanError("dirty_member")
        a["member_id"], b["member_id"] = b["member_id"], a["member_id"]
        return out
    raise PlanError("bad_step")


def validate_and_apply(slots: list[dict], plan: list[dict], member_ids: list[int], weights: dict[int, int]):
    """在当前格子上顺序校验并应用方案,返回 (new_slots, before, after)。"""
    if not plan:
        raise PlanError("no_plan")
    current = [dict(s) for s in slots]
    before = load_range(project_loads(current, member_ids, weights))
    for step in plan:
        current = _apply_checked(current, step, member_ids)
    after = load_range(project_loads(current, member_ids, weights))
    if after >= before:
        raise PlanError("no_improvement")
    return current, before, after
