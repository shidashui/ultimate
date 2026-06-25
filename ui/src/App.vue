<template>
  <div class="app-root">
    <div class="drag-header">
      <span class="status-text">{{ statusText }}</span>
      <button class="close-btn" @click="onClose">✕</button>
    </div>

    <Transition name="fade">
      <div v-if="ui.active" class="waveform-container" key="waveform">
        <div class="waveform-placeholder">◉</div>
        <div class="mode-label">{{ modeLabel }}</div>
      </div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'

const ui = ref({ active: false })

const statusText = computed(() => '◉ JARVIS Online')
const modeLabel = computed(() => '待命中')

function onClose() {}
</script>

<style scoped>
.app-root {
  width: 100%; height: 100%;
  display: flex; flex-direction: column;
  background: linear-gradient(135deg, #0a0a1a 0%, #0d0d2b 50%, #0a0a1a 100%);
  padding: 16px;
}
.drag-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 6px 0 12px;
  -webkit-app-region: drag;
}
.status-text { font-size: 12px; color: var(--text-dim); letter-spacing: 2px; }
.close-btn {
  background: none; border: 1px solid rgba(255,255,255,0.1); color: var(--text-dim);
  cursor: pointer; border-radius: 50%; width: 24px; height: 24px; font-size: 12px;
  -webkit-app-region: no-drag;
}
.close-btn:hover { color: var(--accent); border-color: var(--accent-dim); }
.waveform-container {
  flex: 1; display: flex; flex-direction: column;
  align-items: center; justify-content: center;
}
.waveform-placeholder { font-size: 80px; color: var(--accent-dim); }
.mode-label { font-size: 11px; color: var(--text-dim); margin-top: 8px; letter-spacing: 1px; text-transform: uppercase; }
</style>
