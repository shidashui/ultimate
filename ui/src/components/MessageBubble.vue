<template>
  <div :class="['bubble', role, { interrupted: isInterrupted, streaming: isStreaming }]">
    <div class="role-label">{{ role === 'user' ? 'YOU' : 'LUNA' }}</div>
    <div class="bubble-text">
      {{ text }}<span v-if="isStreaming" class="cursor">▊</span>
    </div>
    <div v-if="isInterrupted" class="interrupted-badge">⚡ 连接中断</div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  role: 'user' | 'agent'
  text: string
  isStreaming: boolean
  isInterrupted: boolean
}>()
</script>

<style scoped>
.bubble { margin-bottom: 12px; }
.role-label {
  font-size: 10px; color: var(--text-dim); margin-bottom: 4px;
  text-transform: uppercase; letter-spacing: 1px;
}
.bubble-text {
  padding: 10px 14px; border-radius: 6px; font-size: 13px; line-height: 1.5;
}
.user .bubble-text { background: rgba(0,212,255,0.08); color: var(--text); }
.agent .bubble-text { background: rgba(0,212,255,0.04); color: var(--accent); }
.cursor { animation: blink 1s step-end infinite; }
@keyframes blink { 50% { opacity: 0; } }
.interrupted-badge { font-size: 11px; color: #ff6b6b; margin-top: 4px; }
.interrupted .bubble-text { border: 1px solid rgba(255,107,107,0.3); }
</style>
