<template>
  <div class="app-root">
    <!-- 顶部拖动区域 + 状态 -->
    <div class="drag-header" data-tauri-drag-region>
      <span class="status-text">{{ statusText }}</span>
      <button class="close-btn" @click="onClose">✕</button>
    </div>

    <!-- 波形区：always visible when active -->
    <Transition name="fade">
      <div v-if="state.uiMode !== 'hidden'" class="waveform-container" key="waveform">
        <JarvisWaveform :mode="state.waveformMode" :amplitude="state.amplitude" :size="260" />
        <div class="mode-label">{{ modeLabel }}</div>
      </div>
    </Transition>

    <!-- 对话区：slide-up on conversing/showingData -->
    <Transition name="slide-up">
      <ConversationView
        v-if="state.uiMode === 'conversing' || state.uiMode === 'showingData'"
        :messages="state.messages"
        :visible="true"
      />
    </Transition>

    <!-- 数据表格：fade-in overlay -->
    <Transition name="fade">
      <DataTable
        v-if="state.tableVisible && state.tableData"
        :columns="state.tableData.columns"
        :rows="state.tableData.rows"
        :visible="state.tableVisible"
        @close="state.tableVisible = false"
      />
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { invoke } from '@tauri-apps/api/tauri'
import JarvisWaveform from './components/JarvisWaveform.vue'
import ConversationView from './components/ConversationView.vue'
import DataTable from './components/DataTable.vue'
import { useTauriEvents } from './composables/useTauriEvents'

const { state } = useTauriEvents()

const statusText = computed(() => {
  switch (state.uiMode) {
    case 'hidden':      return '◉ JARVIS Online'
    case 'waveform':    return '🎤 Listening...'
    case 'thinking':    return '◉ Thinking...'
    case 'conversing':  return '◉ Responding'
    case 'showingData': return '◉ Data'
    default:            return '◉ JARVIS'
  }
})

const modeLabel = computed(() => {
  switch (state.waveformMode) {
    case 'breath':  return '待命中'
    case 'pulsate': return '聆听中'
    case 'pulse':   return '思考中'
    case 'active':  return '回复中'
    default:        return ''
  }
})

function onClose() {
  invoke('close_window')
}
</script>

<style scoped>
.app-root {
  width: 100%; height: 100%;
  display: flex; flex-direction: column;
  background: linear-gradient(135deg, #0a0a1a 0%, #0d0d2b 50%, #0a0a1a 100%);
  padding: 14px;
  overflow: hidden;
}

.drag-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 4px 0 10px;
  -webkit-app-region: drag;
}
.status-text { font-size: 12px; color: var(--text-dim); letter-spacing: 2px; }
.close-btn {
  background: none; border: 1px solid rgba(255,255,255,0.1); color: var(--text-dim);
  cursor: pointer; border-radius: 50%; width: 24px; height: 24px; font-size: 12px;
  -webkit-app-region: no-drag;
  display: flex; align-items: center; justify-content: center;
}
.close-btn:hover { color: var(--accent); border-color: var(--accent-dim); }

.waveform-container {
  flex: 1; display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  min-height: 0;
}
.mode-label {
  font-size: 11px; color: var(--text-dim); margin-top: 6px;
  letter-spacing: 1px; text-transform: uppercase;
}
</style>
