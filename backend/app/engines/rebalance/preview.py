"""负荷重平衡预览:只在内存沙盘上找方案,绝不写 assignments。

策略拍板:最速下降贪心。每一步枚举全部合法的「单格改派 / 两格对调」,
取使新极差最小的一步(并列时按确定性键序),直到不存在让极差严格下降的步。
极差是非负整数且每步严格下降,循环必然终止;同一输入必得同一方案,
因此确认时按方案逐步重放即可与预览逐格同钉。

步骤格式(确认时按此校验归属):
- move: {"kind","day","task_id","from_member_id","to_member_id"}  单格改派
- swap: {"kind","a_day","a_task","b_day","b_task","a_member_id","b_member_id"}  两格对调
"""
from app.engines.rebalance.loads import project_loads, load_range


def _canonical(slots: list[dict]) -> list[dict]:
    """只保留定位与归属字段并按 (day, task_id) 排序,保证模拟轨迹确定。"""
    keep = ({"day": s["day"], "task_id": s["task_id"], "member_id": s["member_id"]} for s in slots)
    return sorted(keep, key=lambda s: (s["day"], s["task_id"]))


def _candidates(slots: list[dict], member_ids: list[int]) -> list[dict]:
    """候选步:单格改派(目标须为合格成员,不得引入脏成员)与两格对调(双方均合格)。"""
    steps = []
    ordered = _canonical(slots)
    for s in ordered:
        for mid in member_ids:
            if mid != s["member_id"]:
                steps.append({
                    "kind": "move", "day": s["day"], "task_id": s["task_id"],
                    "from_member_id": s["member_id"], "to_member_id": mid,
                })
    for i in range(len(ordered)):
        for j in range(i + 1, len(ordered)):
            a, b = ordered[i], ordered[j]
            if a["member_id"] == b["member_id"]:
                continue
            if a["member_id"] not in member_ids or b["member_id"] not in member_ids:
                continue
            steps.append({
                "kind": "swap",
                "a_day": a["day"], "a_task": a["task_id"],
                "b_day": b["day"], "b_task": b["task_id"],
                "a_member_id": a["member_id"], "b_member_id": b["member_id"],
            })
    return steps


def _apply_step(slots: list[dict], step: dict) -> list[dict]:
    out = [dict(s) for s in slots]
    if step["kind"] == "move":
        t = next(s for s in out if s["day"] == step["day"] and s["task_id"] == step["task_id"])
        t["member_id"] = step["to_member_id"]
    else:
        a = next(s for s in out if s["day"] == step["a_day"] and s["task_id"] == step["a_task"])
        b = next(s for s in out if s["day"] == step["b_day"] and s["task_id"] == step["b_task"])
        a["member_id"], b["member_id"] = b["member_id"], a["member_id"]
    return out


def _step_key(step: dict) -> tuple:
    """并列时的确定性键序:move 先于 swap,再按格子与目标成员排序。"""
    if step["kind"] == "move":
        return (0, step["day"], step["task_id"], step["to_member_id"])
    return (1, step["a_day"], step["a_task"], step["b_day"], step["b_task"])


def find_plan(slots: list[dict], member_ids: list[int], weights: dict[int, int]):
    """返回 (plan, before, after):plan 为步骤序列;无法严格改进时 plan 为空且 after 为 None。"""
    current = _canonical(slots)
    before = load_range(project_loads(current, member_ids, weights))
    plan = []
    while True:
        cur_range = load_range(project_loads(current, member_ids, weights))
        best = None  # (new_range, step_key, step, new_slots)
        for step in _candidates(current, member_ids):
            nxt = _apply_step(current, step)
            r = load_range(project_loads(nxt, member_ids, weights))
            if r < cur_range and (best is None or (r, _step_key(step)) < (best[0], best[1])):
                best = (r, _step_key(step), step, nxt)
        if best is None:
            break
        plan.append(best[2])
        current = best[3]
    after = load_range(project_loads(current, member_ids, weights))
    if plan and after < before:
        return plan, before, after
    return [], before, None
