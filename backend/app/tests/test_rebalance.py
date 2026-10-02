from app.engines.rebalance import (
    board_fingerprint,
    canonical_slots,
    load_entries,
    plan_rebalance,
    simulate_swaps,
)

WEIGHTS = {1: 1, 2: 2, 3: 3, 4: 4}
NAMES = {1: "阿明", 2: "小雨", 3: "爷爷", 9: "幽灵成员"}


def multistep_board():
    # m1 = 4+3 = 7, m2 = 2+1 = 3, m3 = 2 -> range 5
    # greedy: (0,4)m1 w4 <-> (2,2)m3 w2  => loads 5/3/4 range 2
    # then    (0,3)m1 w3 <-> (1,2)m2 w2  => loads 4/4/4 range 0
    return [
        {"day": 0, "task_id": 3, "member_id": 1},
        {"day": 0, "task_id": 4, "member_id": 1},
        {"day": 1, "task_id": 1, "member_id": 2},
        {"day": 1, "task_id": 2, "member_id": 2},
        {"day": 2, "task_id": 2, "member_id": 3},
    ]


def test_imbalanced_plan_strictly_decreases_range_every_step():
    plan = plan_rebalance(multistep_board(), [1, 2, 3], WEIGHTS, NAMES)
    assert plan["has_plan"] is True
    assert len(plan["swaps"]) == 2
    for st in plan["swaps"]:
        assert st["range_after"] < st["range_before"]
    assert plan["range_before"] == 5
    assert plan["range_after"] == 0
    assert plan["range_after"] < plan["range_before"]
    assert {e["member_id"]: e["load"] for e in plan["loads_after"]} == {1: 4, 2: 4, 3: 4}


def test_balanced_board_empty_plan():
    slots = [
        {"day": 0, "task_id": 1, "member_id": 1},  # w1
        {"day": 0, "task_id": 2, "member_id": 1},  # w2 -> 3
        {"day": 1, "task_id": 3, "member_id": 2},  # w3 -> 3
    ]
    plan = plan_rebalance(slots, [1, 2], WEIGHTS, NAMES)
    assert plan["has_plan"] is False
    assert plan["swaps"] == []
    assert plan["range_before"] == plan["range_after"] == 0
    assert plan["fingerprint_before"] == plan["fingerprint_after"]


def test_dirty_or_inactive_cells_are_frozen():
    slots = [
        {"day": 0, "task_id": 3, "member_id": 1},
        {"day": 0, "task_id": 4, "member_id": 1},  # m1 = 7
        {"day": 1, "task_id": 1, "member_id": 2},
        {"day": 1, "task_id": 2, "member_id": 2},  # m2 = 3
        {"day": 2, "task_id": 2, "member_id": 9},  # ineligible occupant, frozen
    ]
    plan = plan_rebalance(slots, [1, 2], WEIGHTS, NAMES)
    assert plan["has_plan"] is True
    assert plan["range_after"] < plan["range_before"]
    frozen = (2, 2)
    for st in plan["swaps"]:
        assert (st["a_day"], st["a_task"]) != frozen
        assert (st["b_day"], st["b_task"]) != frozen
        assert st["a_member"] in (1, 2) and st["b_member"] in (1, 2)
    final = simulate_swaps(slots, plan["swaps"])
    # no cell is ever handed to an ineligible member...
    assert {s["member_id"] for s in final} == {1, 2, 9}
    # ...and the frozen cell keeps its original occupant
    frozen_cell = next(s for s in final if (s["day"], s["task_id"]) == frozen)
    assert frozen_cell["member_id"] == 9


def test_fingerprint_matches_applied_plan():
    slots = multistep_board()
    plan = plan_rebalance(slots, [1, 2, 3], WEIGHTS, NAMES)
    assert board_fingerprint(slots) == plan["fingerprint_before"]
    final = simulate_swaps(slots, plan["swaps"])
    assert board_fingerprint(final) == plan["fingerprint_after"]


def test_determinism_and_lexicographic_tie_break():
    # m1 owns two weight-2 cells (load 4), m2 owns two weight-1 cells (load 2).
    # All four cross pairs tie at decrease 2; the lexicographically smallest
    # cell pair must win.
    slots = [
        {"day": 0, "task_id": 2, "member_id": 1},
        {"day": 1, "task_id": 2, "member_id": 1},
        {"day": 2, "task_id": 1, "member_id": 2},
        {"day": 3, "task_id": 1, "member_id": 2},
    ]
    first = plan_rebalance(slots, [1, 2], WEIGHTS, NAMES)
    second = plan_rebalance(canonical_slots(slots), [1, 2], WEIGHTS, NAMES)
    assert first == second
    assert len(first["swaps"]) == 1
    st = first["swaps"][0]
    assert (st["a_day"], st["a_task"], st["b_day"], st["b_task"]) == (0, 2, 2, 1)


def test_load_entries_include_zero_load_eligible():
    slots = [{"day": 0, "task_id": 3, "member_id": 1}]  # m1=3, m3 has no cells
    entries = load_entries(slots, [1, 2, 3], WEIGHTS, NAMES)
    by_id = {e["member_id"]: e for e in entries}
    assert [e["member_id"] for e in entries] == [1, 2, 3]
    assert by_id[3]["load"] == 0 and by_id[3]["cells"] == 0
    plan = plan_rebalance(slots, [1, 2, 3], WEIGHTS, NAMES)
    assert plan["range_before"] == 3  # zero-load member anchors the min


def test_too_few_eligible_members_empty_plan():
    slots = [
        {"day": 0, "task_id": 3, "member_id": 1},
        {"day": 1, "task_id": 3, "member_id": 9},
    ]
    plan = plan_rebalance(slots, [1], WEIGHTS, NAMES)
    assert plan["has_plan"] is False
    assert plan["swaps"] == []
