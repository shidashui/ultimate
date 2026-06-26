# Tasks — TTS Network Retry

- [x] **Task 1**: `EdgeTTS.synthesize()` 重试逻辑
  - 最多 3 次重试，指数退避（1s/2s/4s）
  - 文件：`platforms/voice/tts.py`

- [x] **Task 2**: `VoicePlatform._speak()` 广播 error 状态
  - TTSException 时 `_broadcast_status("error", ...)`
  - 文件：`platforms/voice/platform.py`

- [x] **Task 3**: `VoiceConfig` 新增 `tts_retry_count`
  - 文件：`config/configs.py`、`config.yaml`
