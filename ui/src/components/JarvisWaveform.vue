<template>
  <canvas ref="canvasRef" class="waveform-canvas" :width="size" :height="size"></canvas>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import type { WaveformMode } from '../types/events'

const props = defineProps<{
  mode: WaveformMode
  amplitude: number
  size?: number
}>()

const canvasRef = ref<HTMLCanvasElement | null>(null)
let animFrameId = 0
let phase = 0

function draw() {
  const canvas = canvasRef.value
  if (!canvas) return
  const ctx = canvas.getContext('2d')
  if (!ctx) return

  const s = props.size || 280
  const cx = s / 2
  const cy = s / 2

  ctx.clearRect(0, 0, s, s)

  // 波形缩放因子
  let scale = 1.0
  switch (props.mode) {
    case 'pulsate':
      scale = 1.0 + props.amplitude * 0.4 + Math.sin(phase * 2) * 0.05
      break
    case 'pulse':
      scale = 1.0 + Math.sin(phase * 0.8) * 0.08
      break
    case 'active':
      scale = 1.0 + Math.sin(phase * 3) * 0.12
      break
    default: // breath
      scale = 1.0 + Math.sin(phase * 0.3) * 0.02
  }

  // 三层静态环形光晕
  for (let i = 0; i < 3; i++) {
    const r = (55 + i * 18) * scale
    ctx.beginPath()
    ctx.arc(cx, cy, r, 0, Math.PI * 2)
    ctx.strokeStyle = `rgba(0, 212, 255, ${0.1 + i * 0.08})`
    ctx.lineWidth = 1.5
    ctx.stroke()
  }

  // 动态正弦波环
  ctx.beginPath()
  const baseR = 48 * scale
  const waveStrength = props.mode === 'pulsate' ? props.amplitude * 12 : 4
  const waveFreq = props.mode === 'active' ? 6 : 4
  const points = 64
  for (let i = 0; i <= points; i++) {
    const angle = (i / points) * Math.PI * 2
    const distortion = Math.sin(angle * waveFreq + phase) * waveStrength
    const r = baseR + distortion
    const x = cx + Math.cos(angle) * r
    const y = cy + Math.sin(angle) * r
    if (i === 0) ctx.moveTo(x, y)
    else ctx.lineTo(x, y)
  }
  ctx.closePath()
  ctx.strokeStyle = '#00d4ff'
  ctx.lineWidth = 2
  ctx.shadowColor = 'rgba(0, 212, 255, 0.6)'
  ctx.shadowBlur = 12
  ctx.stroke()
  ctx.shadowBlur = 0

  // 中心光点
  ctx.beginPath()
  ctx.arc(cx, cy, 3 * scale, 0, Math.PI * 2)
  ctx.fillStyle = '#00d4ff'
  ctx.shadowColor = 'rgba(0, 212, 255, 0.8)'
  ctx.shadowBlur = 15
  ctx.fill()
  ctx.shadowBlur = 0

  phase += 0.05
  animFrameId = requestAnimationFrame(draw)
}

onMounted(() => { draw() })
onUnmounted(() => { cancelAnimationFrame(animFrameId) })
</script>

<style scoped>
.waveform-canvas {
  display: block;
  margin: 0 auto;
}
</style>
