## Why

语音消息平台 `platforms/voice.py` 当前存在多个性能和质量问题。TTS 使用 `pyttsx3`（SAPI5/ESpeak）每次调用新建引擎，同步阻塞事件循环；唤醒词检测依赖全量 Whisper ASR 做子串匹配，每一次唤醒都要 1-3 秒计算；VAD 使用 2016 年的 `webrtcvad` 规则模型，Mode 3 过于激进容易漏话；整个平台是单体类，录音/STT/TTS/唤醒全部硬编码耦合，无法独立切换后端或测试。

不重构的话，这些问题会随着后续功能增加（多语言 TTS、打断、对话日志）越积越多。

## What Changes

### P0 — TTS 引擎升级（立即生效）
- 用 `edge-tts`（免费、异步、高质量中文 TTS）替换 `pyttsx3`
- 所有 TTS 调用改为 async，不再阻塞事件循环
- 移除 `pyttsx3` 依赖

### P1 — 架构重构
- 将 `VoicePlatform` 拆分为四个独立模块：`AudioIO`（录音/回放）、`STT`（语音识别）、`TTS`（语音合成）、`WakeWord`（唤醒词检测）
- 每个模块声明接口协议，可独立切换后端实现
- `VoicePlatform` 退化为编排器，只负责组装模块和驱动生命周期
- 语音参数（模型大小、VAD 阈值、唤醒词、采样率等）外移到 `config.yaml`，新增 `voice:` 配置节
- VAD 升级：从 `webrtcvad`（规则）替换为 `silero-vad`（深度学习，更高准确率）
- 唤醒词优化：引入轻量级预过滤（Silero VAD 端点检测置信度），仅在疑似唤醒时调用全量 Whisper 确认

## Capabilities

### New Capabilities
- `voice-core`：语音平台核心模块接口定义和参数配置，覆盖 AudioIO / STT / TTS / WakeWord 四大组件接口协议
- `voice-tts-edge`：edge-tts 语音合成适配器，异步调用 Microsoft Edge TTS 服务

### Modified Capabilities
- `agent-identity`：voice 平台作为 agent identity 的一种接入方式，重构后需补充 voice 平台配置关联

## Impact

- `platforms/voice.py` — 重构核心文件（重写）
- `platforms/__init__.py` — 可能需调整导出
- `config.yaml` — 新增 `voice:` 配置节（VAD 参数、唤醒词、模型选择等）
- `config/configs.py` — 新增 `VoiceConfig` dataclass
- `ultimate.py` — gateway 启动参数可能随配置方式调整
- `requirements.txt` — 移除 `pyttsx3`、`webrtcvad`；新增 `edge-tts`（已存在）、`silero-vad`
- `tests/test_voice_platform.py` — 新建测试文件（P0 验收 + P1 模块独立测试）
