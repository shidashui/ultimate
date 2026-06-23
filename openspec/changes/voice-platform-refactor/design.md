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

## 分阶段策略

**P0 — TTS 升级**（第一轮提交）：
- 只改 `voice.py` 中的 `_speak()` 和 `_speak_sync()`
- 替换为 `edge-tts` 异步合成
- 移除 `pyttsx3` 依赖
- 测试：单句 TTS 合成验证

**P1 — 架构重构**（第二轮提交）：
- 新建 `platforms/voice/` 包，含各模块文件
- 保留 `voice.py` 作为向后兼容入口，内部委托到新包
- 重构完成后移除旧 `voice.py`

## 测试策略

- 依赖注入使各模块可独立 mock 测试
- TTS 模块：mock HTTP 请求验证参数构造
- STT 模块：预录测试音频验证转写
- WakeWord 模块：已知正负样本验证检测准确率
- 集成测试：短录音 → 转写 → TTS 全链路
