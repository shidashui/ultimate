# Silero VAD — Frame Size Too Short

## 问题

```
torch.jit.Error: Input audio chunk is too short
builtins.ValueError: Input audio chunk is too short
```

Silero VAD 模型要求 `sr / samples >= 31.25`，即 16000Hz 下至少 512 samples。当前 `FRAME_MS=30` → 480 samples，低于最小值。

## 修复

`FRAME_MS: 30 → 32` → `FRAME_SIZE: 480 → 512`

## 范围

- `platforms/voice/audio.py`
