# Chorerota · 家庭值日轮转

底座:成员+任务 → round-robin 生成周表 → 申请对调 → 确认改表 → 负荷重平衡(预览/确认)。

| 服务 | 端口 |
| --- | --- |
| 前端 | 5100 |
| API | 10100 |

```bash
docker compose up --build
pytest backend/app/tests
```

种子含 clean/dirty。0-1 空桩:`streak_badge` / `skip_week` / `chore_photo`。

## 负荷重平衡

对 **ready** 周可预览局部换格方案,使成员权重负荷**极差严格下降**;草稿/封存周一律拒绝(`week_not_ready`)。

| 端点 | 说明 |
| --- | --- |
| `GET /api/weeks/{id}/loads` | 成员负荷投影(成员页同源) |
| `POST /api/weeks/{id}/rebalance/preview` | 预览:方案 + 极差前后值,**不改 assignments** |
| `POST /api/weeks/{id}/rebalance/confirm` | 确认:校验通过后逐格落表 |

**口径(唯一,`engines/rebalance/loads.py`)**:成员负荷 = 其本周格子上「干净且权重>0」任务的权重和;统计对象为「在岗且干净」成员(含 0 负荷);极差 = 最重 − 最轻。预览、确认、成员页三处共用。

**策略拍板**:最速下降贪心(`engines/rebalance/preview.py`)——每步枚举全部合法「单格改派 + 两格对调」,取新极差最小者(并列按确定性键序),直至无严格改进;极差为非负整数、每步严格下降,必然终止,且同一输入必得同一方案。

**模块划分**:`loads`(成员负荷投影)/ `preview`(预览寻方案,纯内存)/ `confirm`(校验+应用)分模块,见 `backend/app/engines/rebalance/`。

**确认语义(`engines/rebalance/confirm.py`)**:逐步校验期望归属(不符即 `stale_plan`)、目标成员必须合格(`dirty_member` 拒绝)、应用后极差必须严格下降(`no_improvement` 拒绝)、空方案 `no_plan`;全部通过才逐格 UPDATE 一次提交,任何失败表不变。无法改进时预览声明无方案,确认必失败。
