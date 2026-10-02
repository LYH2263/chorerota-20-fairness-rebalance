"""负荷重平衡 API 流程测例(需 fastapi+httpx,在 docker/CI 内跑)。

覆盖:预览不动 assignments、确认逐格同钉、成员负荷同口径刷新、
无方案时确认必失败且表不变、封存/草稿周拒绝、脏成员拒绝。
"""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.main import app
    with TestClient(app) as c:
        yield c


def _gen(client):
    r = client.post("/api/weeks/1/generate", json={})
    assert r.status_code == 200


def _board(client):
    b = client.get("/api/weeks/1/board").json()
    return sorted((a["day"], a["task_id"], a["member_id"]) for a in b["assignments"])


def _set_status(week_id, status):
    from app.db import connect
    c = connect()
    c.execute("UPDATE weeks SET status=? WHERE id=?", (status, week_id))
    c.commit(); c.close()


def _balance_10_9_9():
    """把第 1 周改成负荷 10/9/9(极差 1,总权重 28 不可均分,必无改进方案)。"""
    from app.db import connect
    c = connect()
    for d in range(7):
        c.execute("UPDATE assignments SET member_id=? WHERE week_id=1 AND day=? AND task_id=3",
                  (1 if d < 5 else 2, d))
        c.execute("UPDATE assignments SET member_id=? WHERE week_id=1 AND day=? AND task_id=1",
                  (2 if d < 5 else 3, d))
        c.execute("UPDATE assignments SET member_id=3 WHERE week_id=1 AND day=? AND task_id=2", (d,))
    c.commit(); c.close()


def test_loads_endpoint_matches_board_projection(client):
    _gen(client)
    payload = client.get("/api/weeks/1/loads").json()
    assert payload["status"] == "ready"
    got = {l["member_id"]: l["load"] for l in payload["loads"]}
    assert set(got) == {1, 2, 3}  # 幽灵成员(脏)不进投影
    weights = {1: 1, 2: 1, 3: 2}
    expect = {m: 0 for m in (1, 2, 3)}
    for d, t, m in _board(client):
        expect[m] += weights[t]
    assert got == expect
    assert payload["range"] == max(expect.values()) - min(expect.values())


def test_preview_does_not_modify_assignments(client):
    _gen(client)
    before = _board(client)
    r = client.post("/api/weeks/1/rebalance/preview")
    assert r.status_code == 200
    assert _board(client) == before


def test_preview_then_confirm_flow_and_loads_refresh(client):
    _gen(client)
    pv = client.post("/api/weeks/1/rebalance/preview").json()
    assert pv["improved"] is True
    assert (pv["before"]["range"], pv["after"]["range"]) == (7, 1)
    assert len(pv["plan"]) == 2
    for s in pv["plan"]:
        assert s["to_member_id"] in (1, 2, 3)  # 不引入脏成员

    r = client.post("/api/weeks/1/rebalance/confirm", json={"plan": pv["plan"]})
    assert r.status_code == 200
    out = r.json()
    assert (out["before_range"], out["after_range"]) == (7, 1)
    assert out["changed_cells"] == 2

    # 看板逐格与预览同钉
    cells = {(d, t): m for d, t, m in _board(client)}
    assert cells[(0, 3)] == 1 and cells[(1, 3)] == 2
    # 成员页负荷与看板同口径刷新
    loads = {l["member_id"]: l["load"] for l in client.get("/api/weeks/1/loads").json()["loads"]}
    assert loads == {1: 9, 2: 9, 3: 10}

    # 同一方案二次确认:格子归属已变,必须 stale 失败且表不变
    snapshot = _board(client)
    r2 = client.post("/api/weeks/1/rebalance/confirm", json={"plan": pv["plan"]})
    assert r2.status_code == 400 and r2.json()["detail"] == "stale_plan"
    assert _board(client) == snapshot


def test_no_improvement_preview_declares_none_and_confirm_fails(client):
    _gen(client)
    _balance_10_9_9()
    pv = client.post("/api/weeks/1/rebalance/preview").json()
    assert pv["improved"] is False
    assert pv["plan"] == [] and pv["after"] is None
    assert pv["before"]["range"] == 1
    assert "无法" in pv["message"]

    snapshot = _board(client)
    r = client.post("/api/weeks/1/rebalance/confirm", json={"plan": []})
    assert r.status_code == 400 and r.json()["detail"] == "no_plan"
    sideways = {"plan": [{"kind": "move", "day": 0, "task_id": 3, "from_member_id": 1, "to_member_id": 2}]}
    r2 = client.post("/api/weeks/1/rebalance/confirm", json=sideways)
    assert r2.status_code == 400 and r2.json()["detail"] == "no_improvement"
    assert _board(client) == snapshot


def test_sealed_and_draft_weeks_rejected(client):
    # 种子第 2 周即封存周
    assert client.post("/api/weeks/2/rebalance/preview").status_code == 400
    # 第 1 周仍是草稿
    assert client.post("/api/weeks/1/rebalance/preview").json()["detail"] == "week_not_ready"
    _gen(client)
    _set_status(1, "sealed")
    assert client.post("/api/weeks/1/rebalance/preview").json()["detail"] == "week_not_ready"
    r = client.post("/api/weeks/1/rebalance/confirm", json={"plan": []})
    assert r.status_code == 400 and r.json()["detail"] == "week_not_ready"


def test_confirm_rejects_plan_introducing_dirty_member(client):
    _gen(client)
    snapshot = _board(client)
    plan = {"plan": [{"kind": "move", "day": 0, "task_id": 1, "from_member_id": 1, "to_member_id": 4}]}
    r = client.post("/api/weeks/1/rebalance/confirm", json=plan)
    assert r.status_code == 400 and r.json()["detail"] == "dirty_member"
    assert _board(client) == snapshot
