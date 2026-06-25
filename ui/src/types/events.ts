export interface WakeEvent { event: 'wake' }
export interface SttEvent { event: 'stt'; text: string }
export interface ThinkingEvent { event: 'thinking' }
export interface TextChunkEvent { event: 'text_chunk'; text: string }
export interface DataEvent { event: 'data'; type: 'table'; columns: string[]; rows: any[][] }
export interface AmplitudeEvent { event: 'amplitude'; rms: number }
export interface TtsStartEvent { event: 'tts_start' }
export interface TtsEndEvent { event: 'tts_end' }
export interface IdleEvent { event: 'idle' }
export interface ErrorEvent { event: 'error'; reason: string }

export type BackendEvent = WakeEvent | SttEvent | ThinkingEvent | TextChunkEvent
  | DataEvent | AmplitudeEvent | TtsStartEvent | TtsEndEvent | IdleEvent | ErrorEvent

export interface Message {
  id: number
  role: 'user' | 'agent'
  text: string
  isStreaming: boolean
  isInterrupted: boolean
}

export type UiMode = 'hidden' | 'waveform' | 'thinking' | 'conversing' | 'showingData'
export type WaveformMode = 'breath' | 'pulsate' | 'pulse' | 'active'
