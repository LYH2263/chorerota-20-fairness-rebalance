import hashlib

from app.db import connect


def board_fp(assignments):
    rows = sorted(assignments, key=lambda a: (a["day"], a["task_id"]))
    raw = "\n".join(f"{r['day']},{r['task_id']},{r['member_id']}" for r in rows)
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def snapshot(client):
    a = client.get("/api/weeks/1/board").json()["assignments"]
    return sorted(a, key=lambda r: r["id"])


def generate(client):
    r = client.post("/api/weeks/1/generate", json={})
    assert r.status_code == 200


def confirm_body(preview):
    return {
        "swaps": [
            {"a": {"day": s["a"]["day"], "task_id": s["a"]["task_id"]},
             "b": {"day": s["b"]["day"], "task_id": s["b"]["task_id"]}}
            for s in preview["swaps"]
        ],
        "fingerprint_before": preview["fingerprint_before"],
    }


def test_seed_board_preview_shape_and_strict_decrease(client):
    generate(client)
    loads = client.get("/api/weeks/1/loads").json()
    assert loads["range"] == 7

    r = client.post("/api/weeks/1/rebalance/preview")
    assert r.status_code == 200
    p = r.json()
    assert p["has_plan"] is True
    assert p["range_before"] == 7
    assert p["range_after"] < p["range_before"]
    assert p["range_after"] == 1  # total load 28 is not divisible by 3
    for s in p["swaps"]:
        assert s["range_after"] < s["range_before"]
    ids = [e["member_id"] for e in p["loads_after"]]
    assert ids == sorted(ids) and len(ids) == 3
    assert {e["member_id"]: e["load"] for e in p["loads_after"]} == {1: 9, 2: 9, 3: 10}


def test_preview_does_not_mutate(client):
    generate(client)
    before = snapshot(client)
    client.post("/api/weeks/1/rebalance/preview")
    after = snapshot(client)
    assert before == after


def test_confirm_board_matches_preview_cell_by_cell(client):
    generate(client)
    p = client.post("/api/weeks/1/rebalance/preview").json()
    r = client.post("/api/weeks/1/rebalance/confirm", json=confirm_body(p))
    assert r.status_code == 200, r.text
    ack = r.json()
    assert ack["applied"] == len(p["swaps"])

    board = client.get("/api/weeks/1/board").json()["assignments"]
    fp_after = board_fp(board)
    assert fp_after == p["fingerprint_after"] == ack["fingerprint_after"]


def test_loads_endpoint_matches_preview_after(client):
    generate(client)
    p = client.post("/api/weeks/1/rebalance/preview").json()
    client.post("/api/weeks/1/rebalance/confirm", json=confirm_body(p))
    proj = client.get("/api/weeks/1/loads").json()
    ack = client.post("/api/weeks/1/rebalance/preview").json()  # now has_plan False
    assert ack["has_plan"] is False
    assert proj["range"] == p["range_after"]
    assert proj["loads"] == p["loads_after"]


def test_second_confirm_fails_and_board_unchanged(client):
    generate(client)
    p = client.post("/api/weeks/1/rebalance/preview").json()
    body = confirm_body(p)
    assert client.post("/api/weeks/1/rebalance/confirm", json=body).status_code == 200
    settled = snapshot(client)

    r = client.post("/api/weeks/1/rebalance/confirm", json=body)
    assert r.status_code == 400 and r.json()["detail"] == "no_improving_swap"
    assert snapshot(client) == settled

    r2 = client.post("/api/weeks/1/rebalance/confirm", json={"swaps": [], "fingerprint_before": None})
    assert r2.status_code == 400 and r2.json()["detail"] == "no_improving_swap"
    assert snapshot(client) == settled


def test_stale_plan_rejected_without_mutation(client):
    generate(client)
    p = client.post("/api/weeks/1/rebalance/preview").json()
    before = snapshot(client)

    tampered = confirm_body(p)
    tampered["swaps"][0]["a"]["task_id"] = p["swaps"][0]["b"]["task_id"]
    r = client.post("/api/weeks/1/rebalance/confirm", json=tampered)
    assert r.status_code == 400 and r.json()["detail"] == "plan_stale"
    assert snapshot(client) == before

    wrong_fp = confirm_body(p)
    wrong_fp["fingerprint_before"] = "sha256:deadbeef"
    r2 = client.post("/api/weeks/1/rebalance/confirm", json=wrong_fp)
    assert r2.status_code == 400 and r2.json()["detail"] == "plan_stale"
    assert snapshot(client) == before


def test_sealed_week_cannot_be_balanced_but_loads_still_viewable(client):
    generate(client)
    assert client.post("/api/weeks/1/seal").status_code == 200

    r = client.post("/api/weeks/1/rebalance/preview")
    assert r.status_code == 400 and r.json()["detail"] == "week_sealed"
    r = client.post("/api/weeks/1/rebalance/confirm", json={"swaps": []})
    assert r.status_code == 400 and r.json()["detail"] == "week_sealed"
    assert client.post("/api/weeks/1/generate", json={}).status_code == 400

    assert client.post("/api/weeks/1/seal").status_code == 400

    # seeded sealed, board-less week 2
    assert client.post("/api/weeks/2/rebalance/preview").status_code == 400
    loads = client.get("/api/weeks/2/loads")
    assert loads.status_code == 200
    assert loads.json()["range"] == 0


def test_draft_and_empty_board_rejected(client):
    r = client.post("/api/weeks/1/rebalance/preview")
    assert r.status_code == 400 and r.json()["detail"] == "week_not_ready"

    c = connect()
    c.execute("INSERT INTO weeks(label,status) VALUES ('空周','ready')")
    c.commit(); c.close()
    r2 = client.post("/api/weeks/3/rebalance/preview")
    assert r2.status_code == 400 and r2.json()["detail"] == "week_not_ready"


def test_seal_transitions(client):
    assert client.post("/api/weeks/1/seal").status_code == 400  # draft
    generate(client)
    assert client.post("/api/weeks/1/seal").status_code == 200
    assert client.get("/api/weeks").json()[0]["status"] == "sealed"
