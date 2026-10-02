<template>
  <div>
    <h1 class="brand">成员</h1>
    <p v-if="loads" class="muted">本周负荷(与看板同口径)· 极差 {{ loads.range }}</p>
    <form @submit.prevent="add">
      <input v-model="name" placeholder="新成员姓名" />
      <button type="submit">添加</button>
    </form>
    <ul class="list">
      <li v-for="m in rows" :key="m.id">
        <strong>{{ m.name }}</strong>
        <span class="muted"> · {{ m.active ? '在岗' : '停用' }} · {{ m.data_quality }}</span>
        <span v-if="loadOf(m.id) !== null" class="chip coral" style="margin-left:6px">负荷 {{ loadOf(m.id) }}</span>
        <span v-else class="muted"> · 不参与负荷统计</span>
      </li>
    </ul>
  </div>
</template>
<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api'
const rows = ref([])
const loads = ref(null)
const name = ref('')
const weekId = 1
function loadOf(id) {
  if (!loads.value) return null
  const hit = loads.value.loads.find(l => l.member_id === id)
  return hit ? hit.load : null
}
async function load() {
  rows.value = await api('/members')
  try { loads.value = await api('/weeks/' + weekId + '/loads') } catch { loads.value = null }
}
async function add() {
  if (!name.value.trim()) return
  await api('/members', { method: 'POST', body: JSON.stringify({ name: name.value }) })
  name.value = ''; await load()
}
onMounted(load)
</script>
