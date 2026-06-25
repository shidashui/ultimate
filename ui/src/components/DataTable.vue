<template>
  <Transition name="fade">
    <div v-if="visible" class="data-table panel">
      <div class="table-header">
        <span>DATA</span>
        <button class="close-btn" @click="$emit('close')">✕</button>
      </div>
      <table>
        <thead>
          <tr><th v-for="col in columns" :key="col">{{ col }}</th></tr>
        </thead>
        <tbody>
          <tr v-for="(row, i) in rows" :key="i">
            <td v-for="(cell, j) in row" :key="j">{{ cell }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </Transition>
</template>

<script setup lang="ts">
defineProps<{
  columns: string[]
  rows: any[][]
  visible: boolean
}>()

defineEmits<{
  close: []
}>()
</script>

<style scoped>
.data-table { padding: 12px; margin-top: 10px; }
.table-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 8px; font-size: 10px; color: var(--text-dim);
  text-transform: uppercase; letter-spacing: 1px;
}
.close-btn {
  background: none; border: 1px solid var(--accent-dim); color: var(--accent);
  cursor: pointer; border-radius: 4px; padding: 2px 8px; font-size: 12px;
}
.close-btn:hover { background: rgba(0,212,255,0.1); }
table { width: 100%; border-collapse: collapse; font-size: 12px; }
th {
  text-align: left; padding: 6px 10px;
  border-bottom: 2px solid var(--accent-dim); color: var(--accent);
}
td {
  padding: 5px 10px; border-bottom: 1px solid rgba(0,212,255,0.08);
  color: var(--text);
}
tr:nth-child(even) td { background: rgba(0,212,255,0.03); }
</style>
