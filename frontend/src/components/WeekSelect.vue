<template>
  <select :value="modelValue" class="week-select" @change="onChange">
    <option v-for="w in weeks" :key="w.id" :value="w.id">
      #{{ w.id }} {{ w.label }}（{{ statusText(w.status) }}）
    </option>
  </select>
</template>
<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api'

const props = defineProps({ modelValue: Number })
const emit = defineEmits(['update:modelValue'])
const weeks = ref([])

function statusText(s) {
  return { draft: '草稿', ready: '已生成', sealed: '已封存' }[s] || s
}
function onChange(e) {
  emit('update:modelValue', Number(e.target.value))
}
onMounted(async () => {
  weeks.value = await api('/weeks')
})
</script>
<style scoped>
.week-select { width: auto; min-width: 170px; margin: 0; }
</style>
