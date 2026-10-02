"""成员负荷投影:看板格子 × 任务权重 → 每成员负荷与极差(全站唯一口径)。

预览、确认、成员页三处都只用这里的函数,保证口径一致:
- 参与统计的成员:在岗(active=1)且数据干净(data_quality='clean'),含 0 负荷成员;
- 参与统计的任务:干净且权重为正,与 generate 的选任务口径相同;
- 成员负荷 = 其本周格子上合格任务的权重和;极差 = 最重负荷 − 最轻负荷。
"""

def eligible_member_ids(members: list[dict]) -> list[int]:
    """参与负荷统计的成员 id:在岗且干净。脏成员/停用成员不进入投影。"""
    return [m["id"] for m in members if m["active"] == 1 and m["data_quality"] == "clean"]


def weight_map(tasks: list[dict]) -> dict[int, int]:
    """参与负荷统计的任务权重:干净且权重为正。"""
    return {t["id"]: t["weight"] for t in tasks if t["data_quality"] == "clean" and t["weight"] > 0}


def project_loads(slots: list[dict], member_ids: list[int], weights: dict[int, int]) -> dict[int, int]:
    """每个合格成员的负荷 = 其格子上合格任务的权重和;未上榜成员计 0。"""
    loads = {mid: 0 for mid in member_ids}
    for s in slots:
        if s["member_id"] in loads:
            loads[s["member_id"]] += weights.get(s["task_id"], 0)
    return loads


def load_range(loads: dict[int, int]) -> int:
    """极差 = 最重负荷 − 最轻负荷;无成员时为 0。"""
    if not loads:
        return 0
    vals = list(loads.values())
    return max(vals) - min(vals)
