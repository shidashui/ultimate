# Voice Platform Full-Chain Fix — Technical Design

## 核心决策

### 1. 反馈体系：事件驱动 + status 回调

不再使用 `print()` 或 `logger.info()` 给用户反馈。改为通过 status callback 模式：

```python
# 每个组件接受可选的 status_callback: Callable[[str, str], Awaitable[None]]
# 参数：(stage: str, detail: str)
# stage: "loading" | "listening" | "transcribing" | "thinking" | "speaking" | "idle" | "error"

async def _broadcast_status(self, stage: str, detail: str = "") -> None:
    """向 Tauri GUI 广播状态事件，同时 print 到终端。"""
    if self._tauri_platform:
        await self._tauri_platform.broadcast({"event": "status", "stage": stage, "detail": detail})
    print(f"[Voice] {stage}: {detail}", flush=True)
```

**广播时机**：

| 阶段 | stage | 触发位置 |
|------|-------|---------|
| Whisper 加载中 | `loading` | `WhisperSTT._get_model()` 前后 |
| Silero 下载中 | `loading` | `SileroAudioIO._record_sync()` torch.hub.load 前后 |
| 等待唤醒词 | `listening` | `TwoStageWakeWord.wait_for_wake()` 循环每次迭代 |
| STT 转录中 | `transcribing` | `WhisperSTT._transcribe_sync()` 前后 |
| LLM 思考中 | `thinking` | Gateway `_handle_message()` 内 |
| TTS 合成中 | `speaking` | `VoicePlatform._speak()` 前后 |
| 空闲 | `idle` | 交互完成时 |

### 2. torch.hub.load 超时保护

```python
# audio.py — _record_sync()
import signal  # or asyncio.wait_for wrapping the executor

# 方案：使用 asyncio.wait_for + run_in_executor 超时控制
# record_utterance 已经在 executor 中运行，外层加上超时：

async def record_utterance(self, vad_threshold=0.5, max_secs=30, download_timeout=10.0):
    loop = asyncio.get_event_loop()
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(None, self._record_sync, threshold, max_secs),
            timeout=max_secs + download_timeout + 5  # 总超时
        )
    except asyncio.TimeoutError:
        logger.error("record_utterance timed out")
        return None
```

同时为 `torch.hub.load()` 添加预检查 — 启动时异步预热模型，超时则直接降级到振幅 VAD。

### 3. 消除双重转录

**现状**：唤醒词检测转录一次 + 指令转录一次 = 两次 STT。

**方案**：在唤醒词检测阶段，转录结果同时包含唤醒词 + 可能的指令内容。如果用户说 "你好，今天天气怎么样"，第一次转录就能拿到完整文本。从中分离唤醒词后的指令部分。

```python
# wake.py — wait_for_wake() 新逻辑
async def wait_for_wake(self) -> str | None:
    while True:
        audio = await self._audio.record_utterance()
        if audio is None:
            continue
        
        text = await self._stt.transcribe(audio)
        
        # 查找唤醒词位置
        idx = text.find(self._wake_word)
        if idx >= 0:
            # 唤醒词之后的内容 = 指令
            command = text[idx + len(self._wake_word):].strip()
            if command:
                return command  # 不需要二次录音！
            else:
                # 只有唤醒词，等待指令
                return await self.record_command()
```

**效果**：当用户在唤醒词后立即说出指令时，节省一次完整的 STT 转录（5-15s）。

### 4. STT 参数优化

```python
# stt.py — _transcribe_sync()
segments, _ = model.transcribe(
    buf,
    language=language,
    vad_filter=False,        # 关闭冗余 VAD（Silero 已过滤）
    beam_size=3,              # 从 5 降到 3
    initial_prompt="以下是普通话日常对话。",
)
```

**效果估算**：`vad_filter=False` 减少 ~20% 耗时，`beam_size: 5→3` 减少 ~15% 耗时。

### 5. 忙等优化

```python
# platform.py — _listen_loop()
# 现状:
while self._speaking:
    await asyncio.sleep(0.05)

# 改为事件驱动:
self._speak_done = asyncio.Event()

# _speak() 结束时:
self._speak_done.set()

# _listen_loop() 中:
await self._speak_done.wait()
self._speak_done.clear()
```

### 6. 新增配置项

```yaml
# config.yaml — voice:
voice:
  model: small                    # 现有
  vad: silero                     # 现有
  vad_threshold: 0.5              # 现有
  wake_word: "你好"               # 现有
  sample_rate: 16000              # 现有
  max_record_secs: 30             # 现有
  tts_voice: zh-CN-XiaoxiaoNeural # 现有
  # 新增 ─────────────────────
  stt_beam_size: 3                # beam search 宽度（原硬编码 5）
  stt_vad_filter: false           # 是否在 STT 内部启用 VAD（原硬编码 True）
  silero_download_timeout: 15     # Silero 模型下载超时（秒）
  stt_model_warmup: true          # 启动时预热 STT 模型
  status_verbose: true            # 是否启用终端状态打印
```

### 7. VoiceConfig 更新

```python
@dataclass
class VoiceConfig:
    model: str = "small"
    vad: str = "silero"
    vad_threshold: float = 0.5
    wake_word: str = "你好"
    sample_rate: int = 16000
    max_record_secs: int = 30
    tts_voice: str = "zh-CN-XiaoxiaoNeural"
    # 新增
    stt_beam_size: int = 3
    stt_vad_filter: bool = False
    silero_download_timeout: int = 15
    stt_model_warmup: bool = True
    status_verbose: bool = True
```

## 数据流变化

```
改造前（双重转录）:
  Mic → VAD 候选 → STT 转录 #1 → 唤醒词匹配?
    → YES → 再录音 → STT 转录 #2 → 指令文本 → Agent
  ⏱ STT 总耗时: 10-30s

改造后（智能分离）:
  Mic → VAD 候选 → STT 转录 #1 → 唤醒词匹配 + 指令分离
    → 有指令 → 直接送 Agent
    → 无指令 → 再录音 → STT 转录 #2 → 指令文本 → Agent
  ⏱ STT 总耗时: 5-15s（常见情况）/ 10-30s（仅唤醒词时）
```

## 文件变更清单

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `platforms/voice/audio.py` | 修改 | torch.hub.load 超时、VAD 状态回调 |
| `platforms/voice/stt.py` | 修改 | beam_size 优化、vad_filter 关闭、状态回调 |
| `platforms/voice/wake.py` | 修改 | 智能指令分离、超时处理、状态回调 |
| `platforms/voice/platform.py` | 修改 | 统一状态广播、忙等改事件驱动 |
| `gateway/events.py` | 修改 | 新增 status 事件 |
| `config/configs.py` | 修改 | VoiceConfig 新增字段 |
| `config.yaml` | 修改 | voice 段新增配置项 |
| `tests/test_voice_platform.py` | 修改 | 新增测试用例 |
