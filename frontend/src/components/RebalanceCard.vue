<template>
  <article class="week-card" style="margin:12px 0">
    <header>重平衡预览</header>
    <template v-if="!data.has_plan">
      <p class="muted">无方案：当前周表已是局部最优，两两对调无法严格降低极差。</p>
    </template>
    <template v-else>
      <p>
        极差
        <strong>{{ data.range_before }}</strong>
        →
        <strong class="coral-text">{{ data.range_after }}</strong>
      </p>
      <ul class="list">
        <li v-for="s in data.swaps" :key="s.step">
          <span class="chip gray">{{ s.step }}</span>
          Day {{ s.a.day }} {{ s.a.task_title }}（权重 {{ s.a.weight }}）{{ s.a.member_name }}
          <span class="muted">↔</span>
          Day {{ s.b.day }} {{ s.b.task_title }}（权重 {{ s.b.weight }}）{{ s.b.member_name }}
          <span class="chip">极差 {{ s.range_before }}→{{ s.range_after }}</span>
        </li>
      </ul>
      <p class="muted" style="margin-top:8px">各成员加权负荷 before→after：</p>
      <ul class="list">
        <li v-for="(b, i) in data.loads_before" :key="b.member_id">
          <strong>{{ b.member_name }}</strong>
          <span class="muted">
            · 负荷 {{ beforeOf(b.member_id).load }}→{{ afterOf(b.member_id).load }}
            · 格数 {{ afterOf(b.member_id).cells }}
          </span>
        </li>
      </ul>
      <button style="margin-top:10px" :disabled="busy" @click="$emit('confirm')">
        {{ busy ? '执行中…' : '确认执行重平衡' }}
      </button>
    </template>
  </article>
</template>
<script setup>
const props = defineProps({ data: Object, busy: Boolean })
defineEmits(['confirm'])

function afterOf(id) {
  return props.data.loads_after.find(e => e.member_id === id) || {}
}
function beforeOf(id) {
  return props.data.loads_before.find(e => e.member_id === id) || {}
}
</script>
