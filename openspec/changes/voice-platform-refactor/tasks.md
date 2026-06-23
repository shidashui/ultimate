# Tasks: voice-platform-refactor

## P0 — TTS 引擎升级

- [x] **Task 1**: 替换 `_speak()` / `_speak_sync()` 为 edge-tts 异步调用，移除 pyttsx3
- [x] **Task 2**: 验证 TTS 输出（单句合成 + 播放测试），更新 requirements.txt 去掉 pyttsx3

## P1 — 架构重构

- [x] **Task 3**: 在 `config.yaml` 新增 `voice:` 配置节，`configs.py` 新增 `VoiceConfig` dataclass
- [x] **Task 4**: 新建 `platforms/voice/` 包，定义四大 Protocol 接口
- [x] **Task 5**: 实现 `AudioIO` 模块（录音 + VAD 端点检测，使用 Silero-VAD）
- [x] **Task 6**: 实现 `STT` 模块（faster-whisper 封装，去掉临时 WAV 文件，使用内存管道）
- [x] **Task 7**: 实现 `TTS` 模块（edge-tts 封装）
- [x] **Task 8**: 实现两阶段 `WakeWord` 模块（Silero VAD 预过滤 + Whisper 确认）
- [x] **Task 9**: 重写 `VoicePlatform` 为编排器，组合四模块，删除旧 voice.py
- [x] **Task 10**: 更新 `ultimate.py` gateway_cmd() 使用新的配置驱动方式
- [x] **Task 11**: 编写测试文件 `tests/test_voice_platform.py`（模块单元测试 + 集成测试）
