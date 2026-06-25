import { reactive } from 'vue'
import { listen } from '@tauri-apps/api/event'
import type { Message, UiMode, WaveformMode } from '../types/events'

export function useTauriEvents() {
  const state = reactive({
    uiMode: 'hidden' as UiMode,
    waveformMode: 'breath' as WaveformMode,
    amplitude: 0,
    messages: [] as Message[],
    messageIdCounter: 0,
    currentStreamingId: -1,
    tableData: null as { columns: string[]; rows: any[][] } | null,
    tableVisible: false,
    idleTimer: null as ReturnType<typeof setTimeout> | null,
  })

  function startIdleTimer() {
    clearIdleTimer()
    state.idleTimer = setTimeout(() => {
      state.uiMode = 'hidden'
      state.waveformMode = 'breath'
      state.currentStreamingId = -1
      state.tableVisible = false
    }, 10000)
  }

  function clearIdleTimer() {
    if (state.idleTimer) {
      clearTimeout(state.idleTimer)
      state.idleTimer = null
    }
  }

  async function setupListeners() {
    await listen<string>('tauri://wake', () => {
      clearIdleTimer()
      state.uiMode = 'waveform'
      state.waveformMode = 'pulsate'
    })

    await listen<string>('tauri://stt', (e) => {
      clearIdleTimer()
      const payload = JSON.parse(e.payload)
      state.messages.push({
        id: ++state.messageIdCounter, role: 'user',
        text: payload.text, isStreaming: false, isInterrupted: false,
      })
      state.uiMode = 'thinking'
      state.waveformMode = 'pulse'
    })

    await listen<string>('tauri://thinking', () => {
      clearIdleTimer()
      state.uiMode = 'thinking'
      state.waveformMode = 'pulse'
    })

    await listen<string>('tauri://text-chunk', (e) => {
      clearIdleTimer()
      const payload = JSON.parse(e.payload)
      if (state.uiMode !== 'conversing' && state.uiMode !== 'showingData') {
        state.uiMode = 'conversing'
      }

      if (state.currentStreamingId < 0) {
        state.currentStreamingId = ++state.messageIdCounter
        state.messages.push({
          id: state.currentStreamingId, role: 'agent',
          text: payload.text, isStreaming: true, isInterrupted: false,
        })
      } else {
        const msg = state.messages.find(m => m.id === state.currentStreamingId)
        if (msg) msg.text += payload.text
      }
    })

    await listen<string>('tauri://data', (e) => {
      clearIdleTimer()
      const payload = JSON.parse(e.payload)
      state.tableData = { columns: payload.columns, rows: payload.rows }
      state.tableVisible = true
      state.uiMode = 'showingData'
    })

    await listen<string>('tauri://amplitude', (e) => {
      const payload = JSON.parse(e.payload)
      state.amplitude = payload.rms
    })

    await listen<string>('tauri://tts-start', () => {
      clearIdleTimer()
      state.waveformMode = 'active'
    })

    await listen<string>('tauri://tts-end', () => {
      state.waveformMode = 'breath'
    })

    await listen<string>('tauri://idle', () => {
      state.currentStreamingId = -1
      state.waveformMode = 'breath'
      startIdleTimer()
    })

    await listen<string>('tauri://error', (e) => {
      const payload = JSON.parse(e.payload)
      if (state.currentStreamingId >= 0) {
        const msg = state.messages.find(m => m.id === state.currentStreamingId)
        if (msg) {
          msg.isInterrupted = true
          msg.isStreaming = false
        }
        state.currentStreamingId = -1
      }
    })
  }

  setupListeners()
  return { state }
}
