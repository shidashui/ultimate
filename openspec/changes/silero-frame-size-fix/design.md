# Silero Frame Size Fix — Design

## 修复

`FRAME_MS = 30 → 32`，使 `FRAME_SIZE = 16000 * 32 / 1000 = 512`，满足 Silero VAD 最小值要求（`sr / 512 = 31.25`）。
