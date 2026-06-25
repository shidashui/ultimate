<template>
  <div v-if="conversationVisible" class="conversation-view panel">
    <div class="conv-header">对话</div>
    <div class="conv-messages" ref="scrollRef">
      <MessageBubble
        v-for="msg in messages" :key="msg.id"
        :role="msg.role" :text="msg.text"
        :isStreaming="msg.isStreaming" :isInterrupted="msg.isInterrupted"
      />
    </div>
    <InputBar />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch, nextTick } from 'vue'
import MessageBubble from './MessageBubble.vue'
import InputBar from './InputBar.vue'
import type { Message } from '../types/events'

const props = defineProps<{
  messages: Message[]
  visible: boolean
}>()

const scrollRef = ref<HTMLElement | null>(null)
const conversationVisible = computed(() =>
  props.visible && props.messages.length > 0
)

watch(() => props.messages.length, async () => {
  await nextTick()
  if (scrollRef.value) {
    scrollRef.value.scrollTop = scrollRef.value.scrollHeight
  }
})
</script>

<style scoped>
.conversation-view {
  padding: 12px;
  display: flex; flex-direction: column;
  max-height: 320px; min-height: 100px;
  margin-top: 10px;
}
.conv-header {
  font-size: 10px; color: var(--text-dim);
  text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px;
}
.conv-messages {
  flex: 1; overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: var(--accent-dim) transparent;
}
.conv-messages::-webkit-scrollbar { width: 4px; }
.conv-messages::-webkit-scrollbar-thumb { background: var(--accent-dim); border-radius: 2px; }
</style>
