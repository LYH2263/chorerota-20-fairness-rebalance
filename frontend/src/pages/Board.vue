<template>
  <div>
    <div class="row-between">
      <h1 class="brand" style="margin:0">本周看板</h1>
      <span class="chip" :class="statusClass">{{ statusText }}</span>
    </div>
    <p class="muted">周卡片网格 · ready 周可预览局部换格重平衡，封存周不可改</p>
    <div class="row-between" style="margin:12px 0">
      <WeekSelect v-model="weekId" />
      <span style="display:flex;gap:8px">
        <button :disabled="sealed" @click="generate">生成周表</button>
        <button class="ghost" @click="load">刷新</button>
        <button :disabled="status !== 'ready'" @click="seal">封存</button>
        <button :disabled="status !== 'ready' || busy" @click="preview">预览重平衡</button>
      </span>
    </div>
    <p v-if="err" class="err">{{ err }}</p>
    <RebalanceCard v-if="plan" :data="plan" :busy="busy" @confirm="confirmPlan" />
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
import { ref, computed, watch, onMounted } from 'vue'
import { api } from '../api'
import WeekSelect from '../components/WeekSelect.vue'
import RebalanceCard from '../components/RebalanceCard.vue'

const assigns = ref([])
const status = ref('')
const weekId = ref(1)
const plan = ref(null)
const busy = ref(false)
const err = ref('')
const days = [0,1,2,3,4,5,6]

const sealed = computed(() => status.value === 'sealed')
const statusText = computed(() => ({ draft: '草稿', ready: '已生成', sealed: '已封存' }[status.value] || status.value))
const statusClass = computed(() => ({ draft: 'gray', ready: 'green', sealed: 'coral' }[status.value] || 'gray'))

function byDay(d) { return assigns.value.filter(a => a.day === d) }

async function load() {
  err.value = ''
  try {
    const b = await api('/weeks/' + weekId.value + '/board')
    assigns.value = b.assignments || []
    status.value = b.week?.status || ''
  } catch (e) { err.value = e.message }
}
async function generate() {
  err.value = ''
  try {
    await api('/weeks/' + weekId.value + '/generate', { method: 'POST', body: '{}' })
    await load()
  } catch (e) { err.value = e.message }
}
async function seal() {
  err.value = ''
  try {
    await api('/weeks/' + weekId.value + '/seal', { method: 'POST', body: '{}' })
    await load()
  } catch (e) { err.value = e.message }
}
async function preview() {
  err.value = ''
  busy.value = true
  try {
    plan.value = await api('/weeks/' + weekId.value + '/rebalance/preview', { method: 'POST', body: '{}' })
  } catch (e) { err.value = e.message } finally { busy.value = false }
}
async function confirmPlan() {
  if (!plan.value?.has_plan) return
  err.value = ''
  busy.value = true
  try {
    const body = {
      swaps: plan.value.swaps.map(s => ({ a: s.a, b: s.b })),
      fingerprint_before: plan.value.fingerprint_before,
    }
    const ack = await api('/weeks/' + weekId.value + '/rebalance/confirm',
      { method: 'POST', body: JSON.stringify(body) })
    if (ack.fingerprint_after !== plan.value.fingerprint_after) {
      throw new Error('落表与预览不一致')
    }
    plan.value = null
    await load()
  } catch (e) { err.value = e.message } finally { busy.value = false }
}

watch(weekId, () => { plan.value = null; load() })
onMounted(load)
</script>
