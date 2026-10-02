<template>
  <div>
    <h1 class="brand">本周看板</h1>
    <p class="muted">周卡片网格 · round-robin 落位后可去「对调」申请交换</p>
    <div style="display:flex;gap:8px;margin:12px 0">
      <button @click="generate">生成周表</button>
      <button class="ghost" @click="load">刷新</button>
      <button class="ghost" @click="preview">预览负荷平衡</button>
    </div>
    <p v-if="err" class="err">{{ err }}</p>
    <p v-if="ok" class="muted">{{ ok }}</p>

    <div v-if="pv" class="week-card" style="margin-bottom:12px">
      <header>负荷重平衡 · 预览(未落表)</header>
      <p>{{ pv.message }}</p>
      <p class="muted">
        成员负荷:
        <span v-for="l in pv.before.loads" :key="l.member_id" class="chip">
          {{ l.name }} {{ l.load }}<template v-if="pv.after"> → {{ afterLoad(l.member_id) }}</template>
        </span>
      </p>
      <ul class="list" v-if="pv.plan.length">
        <li v-for="(s, i) in pv.plan" :key="i">{{ i + 1 }}. {{ describe(s) }}</li>
      </ul>
      <button v-if="pv.improved" @click="confirm">确认执行(逐格落表)</button>
    </div>

    <div class="week-grid">
      <article v-for="d in days" :key="d" class="week-card">
        <header>Day {{ d }}</header>
        <div v-for="a in byDay(d)" :key="a.id">
          <span class="chip">{{ a.task_title }}</span>
          <span class="chip coral">{{ a.member_name }}</span>
        </div>
        <p v-if="!byDay(d).length" class="muted">空</p>
      </article>
    </div>
  </div>
</template>
<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api'
const assigns = ref([])
const days = [0,1,2,3,4,5,6]
const err = ref('')
const ok = ref('')
const pv = ref(null)
const weekId = 1
const ERRS = {
  week_not_ready: '仅「就绪」周可平衡:草稿/封存周不参与',
  no_plan: '无可执行方案',
  no_improvement: '方案无法严格降低极差',
  stale_plan: '方案已过期,请重新预览',
  dirty_member: '方案涉及脏成员,已拒绝',
  slot_missing: '格子不存在',
}
function human(e) { return ERRS[e.message] || e.message }
function byDay(d) { return assigns.value.filter(a => a.day === d) }
function afterLoad(mid) {
  const hit = pv.value.after.loads.find(l => l.member_id === mid)
  return hit ? hit.load : '?'
}
function describe(s) {
  if (s.kind === 'move') return `Day ${s.day} · ${s.task_title}(权重${s.weight}):${s.from_name} → ${s.to_name}`
  return `Day ${s.a_day} · ${s.a_task_title} ⇄ Day ${s.b_day} · ${s.b_task_title}:${s.a_name} ↔ ${s.b_name}`
}
async function load() {
  err.value = ''; pv.value = null
  try {
    const b = await api('/weeks/' + weekId + '/board')
    assigns.value = b.assignments || []
  } catch (e) { err.value = human(e) }
}
async function generate() {
  err.value = ''; ok.value = ''
  try { await api('/weeks/' + weekId + '/generate', { method: 'POST', body: '{}' }); await load() }
  catch (e) { err.value = human(e) }
}
async function preview() {
  err.value = ''; ok.value = ''; pv.value = null
  try { pv.value = await api('/weeks/' + weekId + '/rebalance/preview', { method: 'POST', body: '{}' }) }
  catch (e) { err.value = human(e) }
}
async function confirm() {
  err.value = ''; ok.value = ''
  try {
    const r = await api('/weeks/' + weekId + '/rebalance/confirm', {
      method: 'POST', body: JSON.stringify({ plan: pv.value.plan }),
    })
    ok.value = `已逐格落表 ${r.changed_cells} 格,极差 ${r.before_range} → ${r.after_range};成员页负荷同口径刷新`
    pv.value = null
    await load()
  } catch (e) { err.value = human(e) }
}
onMounted(load)
</script>
