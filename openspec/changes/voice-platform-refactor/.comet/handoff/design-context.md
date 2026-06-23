# Comet Design Handoff

- Change: voice-platform-refactor
- Phase: design
- Mode: compact
- Context hash: 93264e38c97abd6070d0f812b3df55200479b9bff5e52755139f8e782d4fb9f7

Generated-by: comet-handoff.sh

OpenSpec remains the canonical capability spec. This handoff is a deterministic, source-traceable context pack, not an agent-authored summary.

## openspec/changes/voice-platform-refactor/proposal.md

- Source: openspec/changes/voice-platform-refactor/proposal.md
- Lines: 1-39
- SHA256: 0295a983bc1c0367812188ed7a55b43d4268cec95583b8c739bc29a3f4742ca7

```md
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
```

## openspec/changes/voice-platform-refactor/design.md

- Source: openspec/changes/voice-platform-refactor/design.md
- Lines: 1-101
- SHA256: fef64bcd935582a19c6350b3ec218570f3b1c0c98b26051eca6b1d3346cac852

[TRUNCATED]

```md
## 方案选型

| 决策 | 选项 | 选择 | 理由 |
|------|------|------|------|
| TTS 引擎 | pyttsx3 / edge-tts / Sherpa-ONNX | **edge-tts** | 异步、高品质中文、零本地依赖、已安装 |
| VAD | webrtcvad (规则) / Silero-VAD (DL) / 自定义 | **Silero-VAD** | 准确率更高，可输出置信度，ML 模型 |
| 唤醒词 | 全量 ASR / 轻量关键词检测 / Porcupine | **两阶段：Silero VAD 预过滤 + Whisper 确认** | 保持准确率 + 降低延迟 |
| ASR | faster-whisper / Sherpa-ONNX / API | **faster-whisper（保持）** | 本地运行、离线可用、质量好 |
| 架构模式 | 单体继承 / 策略模式 / 组件接口 | **接口协议 + 依赖注入** | 可测试、可切换后端 |
| 配置方式 | 硬编码常量 / config.yaml `voice:` 节 | **config.yaml voice: 节** | 统一配置入口 |

## 架构设计

```
                    VoicePlatform（编排器）
                          │
        ┌─────────────────┼──────────────────┐
        ▼                 ▼                   ▼
   ┌─────────┐     ┌───────────┐     ┌───────────┐
   │ AudioIO │◄───►│    STT    │     │    TTS    │◄──── config.yaml
   │ 录音/回放│     │ 语音识别  │     │ 语音合成  │      voice:
   └─────────┘     └─────┬─────┘     └─────┬─────┘      model: base
        │                 │                 │            vad: silero
        ▼                 ▼                 ▼            wake_word: 你好
   ┌─────────┐     ┌───────────┐     ┌───────────┐
   │ BaseAudioIO│  │ BaseSTT   │     │ BaseTTS   │
   │ 接口协议  │  │ 接口协议   │     │ 接口协议   │
   └─────────┘     └───────────┘     └───────────┘
                        │
                   ┌────┴────┐
                   ▼         ▼
            ┌──────────┐  ┌──────────┐
            │WakeWord  │  │WakeWord  │
            │预过滤    │  │Whisper   │
            │(Silero)  │  │确 认     │
            └──────────┘  └──────────┘
```

## 数据流（P1 最终形态）

```
麦克风 → AudioIO (PCM 流)
          │
          ▼
     WakeWord 预过滤 (Silero VAD 置信度)
          │  > 阈值
          ▼
     WakeWord 确认 (Whisper ASR → 子串匹配)
          │  匹配唤醒词
          ▼
     AudioIO 继续录音 → VAD 端点检测 → 完整片段
          │
          ▼
     STT (faster-whisper) → 文本
          │
          ▼
     AgentRunner 处理 → Reply 文本
          │
          ▼
     TTS (edge-tts) → 音频 → AudioIO 播放
```

## 模块协议

每个模块定义一个 Protocol class：

```python
class AudioIOProtocol(Protocol):
    async def record(self, *, vad=VADConfig) -> np.ndarray: ...
    async def play(self, audio: bytes, format: str) -> None: ...

class STTProtocol(Protocol):
    async def transcribe(self, audio: np.ndarray) -> str: ...

class TTSProtocol(Protocol):
    async def synthesize(self, text: str) -> AsyncIterator[bytes]: ...

class WakeWordProtocol(Protocol):
    async def detect(self, audio_stream) -> bool: ...
```
```

Full source: openspec/changes/voice-platform-refactor/design.md

## openspec/changes/voice-platform-refactor/tasks.md

- Source: openspec/changes/voice-platform-refactor/tasks.md
- Lines: 1-18
- SHA256: bff52a652d3a79997a4c24bf6f90e84672b6ae4146961dc1aa1dadc6b544a925

```md
# Tasks: voice-platform-refactor

## P0 — TTS 引擎升级

- [ ] **Task 1**: 替换 `_speak()` / `_speak_sync()` 为 edge-tts 异步调用，移除 pyttsx3
- [ ] **Task 2**: 验证 TTS 输出（单句合成 + 播放测试），更新 requirements.txt 去掉 pyttsx3

## P1 — 架构重构

- [ ] **Task 3**: 在 `config.yaml` 新增 `voice:` 配置节，`configs.py` 新增 `VoiceConfig` dataclass
- [ ] **Task 4**: 新建 `platforms/voice/` 包，定义四大 Protocol 接口
- [ ] **Task 5**: 实现 `AudioIO` 模块（录音 + VAD 端点检测，使用 Silero-VAD）
- [ ] **Task 6**: 实现 `STT` 模块（faster-whisper 封装，去掉临时 WAV 文件，使用内存管道）
- [ ] **Task 7**: 实现 `TTS` 模块（edge-tts 封装）
- [ ] **Task 8**: 实现两阶段 `WakeWord` 模块（Silero VAD 预过滤 + Whisper 确认）
- [ ] **Task 9**: 重写 `VoicePlatform` 为编排器，组合四模块，删除旧 voice.py
- [ ] **Task 10**: 更新 `ultimate.py` gateway_cmd() 使用新的配置驱动方式
- [ ] **Task 11**: 编写测试文件 `tests/test_voice_platform.py`（模块单元测试 + 集成测试）
```

## openspec/changes/voice-platform-refactor/specs/voice-core/spec.md

- Source: openspec/changes/voice-platform-refactor/specs/voice-core/spec.md
- Lines: 1-115
- SHA256: 7005480108e7cc498f2ba600bf5d37f737e48a0ed7dee79c81015717de2fb80b

[TRUNCATED]

```md
# voice-core

Voice platform core module interfaces and configuration-driven architecture.

## ADDED Requirements

### Requirement: Voice platform modular decomposition

The voice platform SHALL be decomposed into four independent modules with protocol interfaces:
- **AudioIOProtocol** — audio capture and playback
- **STTProtocol** — speech-to-text transcription
- **TTSProtocol** — text-to-speech synthesis
- **WakeWordProtocol** — wake word detection

Each module SHALL be independently testable via dependency injection. VoicePlatform SHALL act only as the orchestrator that assembles modules and drives the listen→transcribe→reply→speak lifecycle.

#### Scenario: Module replaces backend independently

- **GIVEN** a VoicePlatform configured with STT backed by faster-whisper
- **WHEN** the STT backend is changed to Sherpa-ONNX
- **THEN** no other module (AudioIO, TTS, WakeWord) requires modification
- **AND** the platform continues to function identically

#### Scenario: Module tested with mock dependency

- **GIVEN** a STTProtocol implementation
- **WHEN** a test injects a pre-recorded audio sample
- **THEN** the STT module transcribes it without requiring actual microphone hardware
- **AND** the test result is deterministic

### Requirement: Voice configuration from config.yaml

Voice platform parameters SHALL be read from `config.yaml` under a `voice:` section, not hardcoded as module-level constants. Parameters include:
- `model`: whisper model size (e.g., `small`, `base`)
- `vad`: VAD backend (`silero`)
- `vad_threshold`: VAD sensitivity (0.0-1.0)
- `wake_word`: wake word phrase
- `sample_rate`: audio sample rate in Hz
- `max_record_secs`: maximum recording duration in seconds
- `tts_voice`: edge-tts voice identifier

#### Scenario: Config changes take effect without code change

- **GIVEN** a running voice platform with wake_word = "你好"
- **WHEN** config.yaml voice.wake_word is changed to "hey" and the platform restarts
- **THEN** the new wake word "hey" is used
- **AND** no Python source file was modified

#### Scenario: Missing config key uses default

- **GIVEN** a config.yaml with voice section omitting `max_record_secs`
- **WHEN** VoiceConfig is loaded
- **THEN** max_record_secs defaults to 30

### Requirement: VAD upgraded to Silero-VAD

Voice Activity Detection SHALL use `silero-vad` (ONNX model) instead of `webrtcvad`. It SHALL output speech probability (0.0-1.0) per frame, enabling confidence-based endpoint decisions.

#### Scenario: Silero VAD detects speech reliably

- **GIVEN** an audio stream containing human speech
- **WHEN** Silero VAD processes the frames
- **THEN** speech probability > 0.5 for speech frames
- **AND** speech probability < 0.5 for silence frames

#### Scenario: VAD endpoint detection stops recording

- **GIVEN** Silero VAD in recording mode with triggered=True
- **WHEN** speech probability drops below threshold for consecutive frames
- **THEN** recording stops and the captured audio segment is returned
- **AND** no trailing silence is included beyond the padding buffer

### Requirement: STT uses in-memory pipeline

Speech-to-text SHALL avoid writing temporary WAV files to disk. Audio data SHALL be passed to faster-whisper via in-memory bytes buffer.

#### Scenario: No temp files created during transcription

- **GIVEN** a numpy audio array
- **WHEN** STT module transcribes it
```

Full source: openspec/changes/voice-platform-refactor/specs/voice-core/spec.md

## openspec/changes/voice-platform-refactor/specs/voice-tts-edge/spec.md

- Source: openspec/changes/voice-platform-refactor/specs/voice-tts-edge/spec.md
- Lines: 1-33
- SHA256: 4b763ac552ec76e9eb6ab7bc9d64443627d134d72d9fdfecf62d5e262dbfd8c2

```md
# voice-tts-edge

edge-tts adapter for text-to-speech synthesis using Microsoft Edge TTS service.

## ADDED Requirements

### Requirement: edge-tts async synthesis

The TTS module SHALL use `edge_tts` for speech synthesis. Synthesis SHALL be asynchronous and SHALL NOT block the asyncio event loop.

#### Scenario: Synthesize Chinese text to audio

- **GIVEN** a TTS instance configured with voice "zh-CN-XiaoxiaoNeural"
- **WHEN** `await tts.synthesize("你好世界")` is called
- **THEN** MP3 audio bytes are returned
- **AND** the audio is playable via sounddevice

#### Scenario: Graceful failure on network error

- **GIVEN** edge-tts service is unreachable (network down)
- **WHEN** `await tts.synthesize("hello")` is called
- **THEN** an error is logged
- **AND** a TTSException is raised with a descriptive message

### Requirement: Voice selection from config

The TTS voice identifier SHALL be read from `config.yaml` `voice.tts_voice` with a default of `zh-CN-XiaoxiaoNeural`.

#### Scenario: Custom voice from config

- **GIVEN** config.yaml voice.tts_voice = "zh-CN-YunxiNeural"
- **WHEN** TTS is initialized
- **THEN** the Yunxi voice is used for synthesis
```

