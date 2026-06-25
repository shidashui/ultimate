<template>
  <div class="input-bar">
    <input
      ref="inputRef"
      v-model="text"
      class="text-input"
      placeholder="输入消息..."
      @keydown.enter="send"
    />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { invoke } from '@tauri-apps/api/tauri'

const text = ref('')

function send() {
  if (!text.value.trim()) return
  invoke('send_input', { text: text.value })
  text.value = ''
}
</script>

<style scoped>
.input-bar { padding: 8px 0 0; }
.text-input {
  width: 100%; padding: 10px 14px;
  background: rgba(0,212,255,0.06); border: 1px solid var(--accent-dim);
  border-radius: 6px; color: var(--text);
  font-family: var(--font-mono); font-size: 13px; outline: none;
}
.text-input:focus { border-color: var(--accent); box-shadow: var(--border-glow); }
.text-input::placeholder { color: var(--text-dim); }
</style>
