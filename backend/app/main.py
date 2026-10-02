import json
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from app import seed
from app.db import connect
from app.engines.rota import build_week_slots, swap_legal, apply_swap
from app.engines.rebalance.loads import eligible_member_ids, weight_map, project_loads, load_range
from app.engines.rebalance.preview import find_plan
from app.engines.rebalance.confirm import validate_and_apply, PlanError

app = FastAPI(title="Chorerota", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.on_event("startup")
def _startup(): seed.init_db()

@app.get("/api/health")
def health(): return {"ok": True, "project": "chorerota"}

@app.get("/api/members")
def list_members():
    c = connect(); rows = [dict(r) for r in c.execute("SELECT * FROM members")]; c.close(); return rows

@app.post("/api/members")
def add_member(body: dict):
    c = connect()
    cur = c.execute("INSERT INTO members(name,active,data_quality) VALUES (?,?,?)",
                    (body.get("name","未命名"), int(body.get("active",1)), body.get("data_quality","clean")))
    c.commit(); mid = cur.lastrowid; c.close(); return {"id": mid}

@app.get("/api/tasks")
def list_tasks():
    c = connect(); rows = [dict(r) for r in c.execute("SELECT * FROM tasks")]; c.close(); return rows

@app.post("/api/tasks")
def add_task(body: dict):
    c = connect()
    cur = c.execute("INSERT INTO tasks(title,weight,data_quality) VALUES (?,?,?)",
                    (body.get("title","任务"), int(body.get("weight",1)), body.get("data_quality","clean")))
    c.commit(); tid = cur.lastrowid; c.close(); return {"id": tid}

@app.get("/api/weeks")
def list_weeks():
    c = connect(); rows = [dict(r) for r in c.execute("SELECT * FROM weeks")]; c.close(); return rows

@app.get("/api/weeks/{week_id}/board")
def week_board(week_id: int):
    c = connect()
    week = c.execute("SELECT * FROM weeks WHERE id=?", (week_id,)).fetchone()
    if not week: c.close(); raise HTTPException(404, "week not found")
    assigns = [dict(r) for r in c.execute("SELECT * FROM assignments WHERE week_id=?", (week_id,))]
    members = {r["id"]: r["name"] for r in c.execute("SELECT id,name FROM members")}
    tasks = {r["id"]: r["title"] for r in c.execute("SELECT id,title FROM tasks")}
    c.close()
    for a in assigns:
        a["member_name"] = members.get(a["member_id"], "?")
        a["task_title"] = tasks.get(a["task_id"], "?")
    return {"week": dict(week), "assignments": assigns}

class GenBody(BaseModel):
    days: int = 7

@app.post("/api/weeks/{week_id}/generate")
def generate(week_id: int, body: GenBody = GenBody()):
    c = connect()
    week = c.execute("SELECT * FROM weeks WHERE id=?", (week_id,)).fetchone()
    if not week: c.close(); raise HTTPException(404, "week not found")
    mids = [r["id"] for r in c.execute("SELECT id FROM members WHERE active=1 AND data_quality='clean' ORDER BY id")]
    tids = [r["id"] for r in c.execute("SELECT id FROM tasks WHERE data_quality='clean' AND weight>0 ORDER BY id")]
    slots = build_week_slots(mids, tids, days=body.days)
    c.execute("DELETE FROM assignments WHERE week_id=?", (week_id,))
    for s in slots:
        c.execute("INSERT INTO assignments(week_id,day,task_id,member_id) VALUES (?,?,?,?)",
                  (week_id, s["day"], s["task_id"], s["member_id"]))
    c.execute("UPDATE weeks SET status='ready' WHERE id=?", (week_id,))
    c.commit(); c.close()
    return {"count": len(slots), "slots": slots}

class SwapBody(BaseModel):
    a_day: int; a_task: int; b_day: int; b_task: int; note: str = ""

@app.post("/api/weeks/{week_id}/swaps")
def request_swap(week_id: int, body: SwapBody):
    c = connect()
    assigns = [dict(r) for r in c.execute("SELECT day,task_id,member_id FROM assignments WHERE week_id=?", (week_id,))]
    check = swap_legal(assigns, body.a_day, body.a_task, body.b_day, body.b_task)
    if not check["ok"]:
        c.close(); raise HTTPException(400, check["reason"])
    cur = c.execute(
        "INSERT INTO swap_requests(week_id,a_day,a_task,b_day,b_task,status,note) VALUES (?,?,?,?,?,?,?)",
        (week_id, body.a_day, body.a_task, body.b_day, body.b_task, "pending", body.note))
    c.commit(); sid = cur.lastrowid; c.close()
    return {"id": sid, "status": "pending", **check}

@app.get("/api/swaps")
def list_swaps():
    c = connect(); rows = [dict(r) for r in c.execute("SELECT * FROM swap_requests ORDER BY id DESC")]; c.close(); return rows

@app.post("/api/swaps/{swap_id}/confirm")
def confirm_swap(swap_id: int):
    c = connect()
    sw = c.execute("SELECT * FROM swap_requests WHERE id=?", (swap_id,)).fetchone()
    if not sw: c.close(); raise HTTPException(404, "swap not found")
    if sw["status"] != "pending":
        c.close(); raise HTTPException(400, "not_pending")
    assigns = [dict(r) for r in c.execute(
        "SELECT id,day,task_id,member_id FROM assignments WHERE week_id=?", (sw["week_id"],))]
    slots = [{"day": a["day"], "task_id": a["task_id"], "member_id": a["member_id"]} for a in assigns]
    try:
        new_slots = apply_swap(slots, sw["a_day"], sw["a_task"], sw["b_day"], sw["b_task"])
    except ValueError as e:
        c.close(); raise HTTPException(400, str(e))
    for a, s in zip(assigns, new_slots):
        c.execute("UPDATE assignments SET member_id=? WHERE id=?", (s["member_id"], a["id"]))
    c.execute("UPDATE swap_requests SET status='confirmed' WHERE id=?", (swap_id,))
    c.commit(); c.close()
    return {"ok": True, "swap_id": swap_id}

# ---- 负荷重平衡:成员负荷投影 / 预览 / 确认(三处共用 engines/rebalance 口径) ----

def _board_context(c, week_id: int):
    week = c.execute("SELECT * FROM weeks WHERE id=?", (week_id,)).fetchone()
    if not week:
        raise HTTPException(404, "week not found")
    members = [dict(r) for r in c.execute("SELECT * FROM members")]
    tasks = [dict(r) for r in c.execute("SELECT * FROM tasks")]
    assigns = [dict(r) for r in c.execute(
        "SELECT * FROM assignments WHERE week_id=? ORDER BY day,task_id", (week_id,))]
    return week, members, tasks, assigns

def _loads_payload(assigns, members, tasks):
    mids = eligible_member_ids(members)
    loads = project_loads(assigns, mids, weight_map(tasks))
    names = {m["id"]: m["name"] for m in members}
    return {
        "loads": [{"member_id": mid, "name": names.get(mid, "?"), "load": loads[mid]} for mid in mids],
        "range": load_range(loads),
    }

@app.get("/api/weeks/{week_id}/loads")
def week_loads(week_id: int):
    c = connect()
    try:
        week, members, tasks, assigns = _board_context(c, week_id)
        return {"week_id": week_id, "status": week["status"], **_loads_payload(assigns, members, tasks)}
    finally:
        c.close()

def _enrich_step(step, members, tasks, weights):
    names = {m["id"]: m["name"] for m in members}
    titles = {t["id"]: t["title"] for t in tasks}
    s = dict(step)
    if s["kind"] == "move":
        s["task_title"] = titles.get(s["task_id"], "?")
        s["weight"] = weights.get(s["task_id"], 0)
        s["from_name"] = names.get(s["from_member_id"], "?")
        s["to_name"] = names.get(s["to_member_id"], "?")
    else:
        s["a_task_title"] = titles.get(s["a_task"], "?")
        s["b_task_title"] = titles.get(s["b_task"], "?")
        s["a_name"] = names.get(s["a_member_id"], "?")
        s["b_name"] = names.get(s["b_member_id"], "?")
    return s

@app.post("/api/weeks/{week_id}/rebalance/preview")
def rebalance_preview(week_id: int):
    c = connect()
    try:
        week, members, tasks, assigns = _board_context(c, week_id)
        if week["status"] != "ready":
            raise HTTPException(400, "week_not_ready")
        mids = eligible_member_ids(members)
        weights = weight_map(tasks)
        plan, before, after = find_plan(assigns, mids, weights)
        resp = {
            "week_id": week_id,
            "improved": bool(plan),
            "before": _loads_payload(assigns, members, tasks),
            "after": None,
            "plan": [],
            "message": "当前排布已无法通过局部换格降低极差",
        }
        if plan:
            new_slots, _, _ = validate_and_apply(assigns, plan, mids, weights)
            resp["after"] = _loads_payload(new_slots, members, tasks)
            resp["plan"] = [_enrich_step(s, members, tasks, weights) for s in plan]
            resp["message"] = f"共 {len(plan)} 步局部换格,极差严格下降 {before} → {after}"
        return resp
    finally:
        c.close()

class RebalanceBody(BaseModel):
    plan: list[dict] = []

@app.post("/api/weeks/{week_id}/rebalance/confirm")
def rebalance_confirm(week_id: int, body: RebalanceBody):
    c = connect()
    try:
        week, members, tasks, assigns = _board_context(c, week_id)
        if week["status"] != "ready":
            raise HTTPException(400, "week_not_ready")
        mids = eligible_member_ids(members)
        weights = weight_map(tasks)
        try:
            new_slots, before, after = validate_and_apply(assigns, body.plan, mids, weights)
        except PlanError as e:
            raise HTTPException(400, e.reason)
        by_key = {(a["day"], a["task_id"]): a for a in assigns}
        changed = 0
        for s in new_slots:
            row = by_key[(s["day"], s["task_id"])]
            if row["member_id"] != s["member_id"]:
                c.execute("UPDATE assignments SET member_id=? WHERE id=?", (s["member_id"], row["id"]))
                changed += 1
        c.commit()
        return {"ok": True, "before_range": before, "after_range": after, "changed_cells": changed}
    finally:
        c.close()

@app.get("/api/settings")
def get_settings():
    c = connect(); rows = {r["key"]: r["value"] for r in c.execute("SELECT * FROM settings")}; c.close(); return rows

@app.put("/api/settings")
def put_settings(body: dict):
    c = connect()
    for k, v in body.items():
        c.execute("INSERT INTO settings(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, str(v)))
    c.commit(); c.close(); return {"ok": True}
