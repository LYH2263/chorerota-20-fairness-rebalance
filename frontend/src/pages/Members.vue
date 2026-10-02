<template>
  <div>
    <h1 class="brand">成员</h1>
    <div class="row-between" style="margin:12px 0">
      <WeekSelect v-model="weekId" />
      <button class="ghost" @click="loadAll">刷新</button>
    </div>
    <p class="muted">加权负荷（任务权重总和） · 极差 <strong>{{ proj.range }}</strong></p>
    <p v-if="err" class="err">{{ err }}</p>
    <ul class="list">
      <li v-for="m in proj.loads" :key="m.member_id">
        <strong>{{ m.member_name }}</strong>
        <span class="chip">负荷 {{ m.load }}</span>
        <span class="chip coral">格数 {{ m.cells }}</span>
      </li>
    </ul>
    <h2 class="brand" style="font-size:16px;margin-top:18px">不参与重平衡（停用 / dirty）</h2>
    <ul class="list">
      <li v-for="m in excluded" :key="m.id" class="muted">
        {{ m.name }} · {{ m.active ? '在岗' : '停用' }} · {{ m.data_quality }}
      </li>
      <li v-if="!excluded.length" class="muted">无</li>
    </ul>
    <form style="margin-top:18px" @submit.prevent="add">
      <input v-model="name" placeholder="新成员姓名" />
      <button type="submit">添加</button>
    </form>
  </div>
</template>
<script setup>
import { ref, watch, onMounted } from 'vue'
import { api } from '../api'
import WeekSelect from '../components/WeekSelect.vue'

const rows = ref([])
const proj = ref({ range: 0, loads: [] })
const weekId = ref(1)
const name = ref('')
const err = ref('')

const excluded = ref([])

async function loadAll() {
  err.value = ''
  try {
    const [members, p] = await Promise.all([
      api('/members'),
      api('/weeks/' + weekId.value + '/loads'),
    ])
    rows.value = members
    proj.value = p
    const eligible = new Set(p.loads.map(e => e.member_id))
    excluded.value = members.filter(m => !eligible.has(m.id))
  } catch (e) { err.value = e.message }
}
async function add() {
  if (!name.value.trim()) return
  await api('/members', { method: 'POST', body: JSON.stringify({ name: name.value }) })
  name.value = ''
  await loadAll()
}
watch(weekId, loadAll)
onMounted(loadAll)
</script>
