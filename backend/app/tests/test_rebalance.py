"""负荷重平衡引擎测例:锁极差严格下降、无方案声明、脏成员/过期方案拒绝。

纯标准库,pytest 与 `python3 app/tests/test_rebalance.py` 均可跑。
"""
from app.engines.rota import build_week_slots
from app.engines.rebalance.loads import (
    eligible_member_ids, weight_map, project_loads, load_range,
)
from app.engines.rebalance.preview import find_plan
from app.engines.rebalance.confirm import validate_and_apply, PlanError

MEMBERS = [
    {"id": 1, "name": "阿明", "active": 1, "data_quality": "clean"},
    {"id": 2, "name": "小雨", "active": 1, "data_quality": "clean"},
    {"id": 3, "name": "爷爷", "active": 1, "data_quality": "clean"},
    {"id": 4, "name": "幽灵成员", "active": 0, "data_quality": "dirty"},
]
TASKS = [
    {"id": 10, "title": "洗碗", "weight": 1, "data_quality": "clean"},
    {"id": 20, "title": "倒垃圾", "weight": 1, "data_quality": "clean"},
    {"id": 30, "title": "扫地", "weight": 2, "data_quality": "clean"},
    {"id": 40, "title": "负权重任务", "weight": -1, "data_quality": "dirty"},
]
MIDS = [1, 2, 3]
WEIGHTS = {10: 1, 20: 1, 30: 2}


def _expect_plan_error(reason, fn, *args):
    try:
        fn(*args)
    except PlanError as e:
        assert e.reason == reason, f"expected {reason}, got {e.reason}"
        return
    raise AssertionError(f"expected PlanError({reason})")


def test_projection_filters_dirty_members_and_tasks():
    assert eligible_member_ids(MEMBERS) == [1, 2, 3]
    assert weight_map(TASKS) == {10: 1, 20: 1, 30: 2}


def test_projection_sums_weights_and_keeps_zero_load():
    slots = [
        {"day": 0, "task_id": 10, "member_id": 1},
        {"day": 1, "task_id": 30, "member_id": 1},
        {"day": 2, "task_id": 40, "member_id": 1},  # 脏任务不计
        {"day": 3, "task_id": 30, "member_id": 4},  # 脏成员不进投影
    ]
    loads = project_loads(slots, MIDS, WEIGHTS)
    assert loads == {1: 3, 2: 0, 3: 0}
    assert load_range(loads) == 3
    assert load_range({}) == 0


def test_find_plan_locks_seed_scenario_decrease():
    """round-robin 种子场景:负荷 7/7/14,锁极差 7 → 1,方案为两步改派。"""
    slots = build_week_slots(MIDS, [10, 20, 30], days=7)
    assert project_loads(slots, MIDS, WEIGHTS) == {1: 7, 2: 7, 3: 14}
    plan, before, after = find_plan(slots, MIDS, WEIGHTS)
    assert (before, after) == (7, 1)
    assert plan == [
        {"kind": "move", "day": 0, "task_id": 30, "from_member_id": 3, "to_member_id": 1},
        {"kind": "move", "day": 1, "task_id": 30, "from_member_id": 3, "to_member_id": 2},
    ]


def test_find_plan_deterministic():
    slots = build_week_slots(MIDS, [10, 20, 30], days=7)
    assert find_plan(slots, MIDS, WEIGHTS) == find_plan(slots, MIDS, WEIGHTS)


def test_find_plan_swap_first_case():
    """锁一个首步为对调的场景:极差 8 → 2。"""
    weights = {10: 1, 11: 5, 12: 2}
    mids = [1, 2, 3, 4]
    slots = [
        {"day": 0, "task_id": 10, "member_id": 2},
        {"day": 0, "task_id": 11, "member_id": 4},
        {"day": 0, "task_id": 12, "member_id": 4},
        {"day": 1, "task_id": 10, "member_id": 3},
        {"day": 1, "task_id": 11, "member_id": 2},
        {"day": 1, "task_id": 12, "member_id": 3},
        {"day": 2, "task_id": 10, "member_id": 1},
        {"day": 2, "task_id": 11, "member_id": 2},
        {"day": 2, "task_id": 12, "member_id": 1},
    ]
    plan, before, after = find_plan(slots, mids, weights)
    assert (before, after) == (8, 2)
    assert plan[0] == {
        "kind": "swap", "a_day": 1, "a_task": 10, "b_day": 1, "b_task": 11,
        "a_member_id": 3, "b_member_id": 2,
    }
    assert plan[1] == {"kind": "move", "day": 0, "task_id": 12, "from_member_id": 4, "to_member_id": 1}


def test_find_plan_no_improvement_declares_no_plan():
    """单重格 + 一名空载成员:极差 2 但任何换格都无法严格下降,须声明无方案。"""
    slots = [{"day": 0, "task_id": 30, "member_id": 1}]
    plan, before, after = find_plan(slots, [1, 2], WEIGHTS)
    assert plan == [] and before == 2 and after is None


def test_plan_never_introduces_dirty_members():
    slots = build_week_slots(MIDS, [10, 20, 30], days=7)
    plan, _, _ = find_plan(slots, MIDS, WEIGHTS)
    for s in plan:
        if s["kind"] == "move":
            assert s["to_member_id"] in MIDS
        else:
            assert s["a_member_id"] in MIDS and s["b_member_id"] in MIDS


def test_validate_and_apply_replays_preview_exactly():
    slots = build_week_slots(MIDS, [10, 20, 30], days=7)
    plan, before, after = find_plan(slots, MIDS, WEIGHTS)
    new_slots, b, a = validate_and_apply(slots, plan, MIDS, WEIGHTS)
    assert (b, a) == (before, after)
    got = {(s["day"], s["task_id"]): s["member_id"] for s in new_slots}
    assert got[(0, 30)] == 1 and got[(1, 30)] == 2


def test_confirm_rejects_empty_plan():
    slots = build_week_slots(MIDS, [10, 20, 30], days=7)
    _expect_plan_error("no_plan", validate_and_apply, slots, [], MIDS, WEIGHTS)


def test_confirm_rejects_stale_plan():
    slots = build_week_slots(MIDS, [10, 20, 30], days=7)
    stale = [{"kind": "move", "day": 0, "task_id": 30, "from_member_id": 2, "to_member_id": 1}]
    _expect_plan_error("stale_plan", validate_and_apply, slots, stale, MIDS, WEIGHTS)


def test_confirm_rejects_dirty_member():
    slots = build_week_slots(MIDS, [10, 20, 30], days=7)
    dirty = [{"kind": "move", "day": 0, "task_id": 10, "from_member_id": 1, "to_member_id": 4}]
    _expect_plan_error("dirty_member", validate_and_apply, slots, dirty, MIDS, WEIGHTS)


def test_confirm_rejects_non_improving_plan():
    slots = build_week_slots(MIDS, [10, 20, 30], days=7)
    sideways = [{"kind": "move", "day": 0, "task_id": 10, "from_member_id": 1, "to_member_id": 2}]
    _expect_plan_error("no_improvement", validate_and_apply, slots, sideways, MIDS, WEIGHTS)


def test_confirm_applies_handmade_swap():
    """对调严格降极差:负荷 2/7/4 → 5/4/4,极差 5 → 1。"""
    weights = {10: 2, 11: 5}
    slots = [
        {"day": 0, "task_id": 10, "member_id": 1},
        {"day": 0, "task_id": 11, "member_id": 2},
        {"day": 1, "task_id": 10, "member_id": 2},
        {"day": 2, "task_id": 10, "member_id": 3},
        {"day": 3, "task_id": 10, "member_id": 3},
    ]
    plan = [{
        "kind": "swap", "a_day": 0, "a_task": 10, "b_day": 0, "b_task": 11,
        "a_member_id": 1, "b_member_id": 2,
    }]
    new_slots, before, after = validate_and_apply(slots, plan, [1, 2, 3], weights)
    assert (before, after) == (5, 1)
    got = {(s["day"], s["task_id"]): s["member_id"] for s in new_slots}
    assert got[(0, 10)] == 2 and got[(0, 11)] == 1


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print("ok", fn.__name__)
    print(f"{len(fns)} engine tests passed")
