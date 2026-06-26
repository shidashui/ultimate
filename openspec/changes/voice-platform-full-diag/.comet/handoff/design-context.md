# Comet Design Handoff

- Change: voice-platform-full-diag
- Phase: design
- Mode: compact
- Context hash: 3eef841bbc2c146ade7931780694af68362bd5d34e2841c544ddd7cba1eafc30

Generated-by: comet-handoff.sh

OpenSpec remains the canonical capability spec. This handoff is a deterministic, source-traceable context pack, not an agent-authored summary.

## openspec/changes/voice-platform-full-diag/proposal.md

- Source: openspec/changes/voice-platform-full-diag/proposal.md
- Lines: 1-56
- SHA256: 76dfa233dbbceddef4d25e4763f11db8fc5ddbdf09664a9092b6b464a73d56f0

```md
# Voice Platform Full-Chain Diagnostic & Fix

## 问题背景

语音平台（`platforms/voice/`）在启动后反应极慢，用户看不到语音处理过程。通过全链路逐行代码追踪，诊断出 7 个性能与体验问题，按严重程度分为 P0-P3。

## 诊断根因

| 优先级 | 问题 | 代码位置 | 现象 |
|--------|------|---------|------|
| **P0** | `torch.hub.load()` 无超时，网络不通时永久挂起 | `audio.py:48` | 用户看到"等待唤醒词"后再无反应 |
| **P0** | 全链路零用户可见进度，全部使用 logger | 整个 `voice/` 模块 | 用户不知道系统在处理还是挂了 |
| **P1** | Whisper 双重转录（唤醒确认 + 指令各一次） | `wake.py:42` + `wake.py:54` | 每次交互多花 5-15s |
| **P1** | STT `vad_filter=True` 冗余（Silero VAD 已过滤） | `stt.py:56` | 增加转录耗时 |
| **P1** | 静默监听时无超时提示或取消机制 | `audio.py:63-92` | 用户不知道系统在监听 |
| **P2** | `beam_size=5` 在 CPU 小模型上性价比低 | `stt.py:58` | 可降至 1-3 |
| **P3** | TTS 期间忙等轮询 `while self._speaking: sleep(0.05)` | `platform.py:110` | 低效但影响较小 |

## 全链路耗时分析

| 阶段 | 冷启动 | 热启动 | 瓶颈 |
|------|--------|--------|------|
| Whisper 模型加载 | 10-30s | 2-5s | 无进度提示 |
| Silero VAD 下载 | 2-5s | ~0.1s | 无超时 |
| STT 唤醒词确认 | 5-15s | 5-15s | 双重转录 |
| 指令录音 + STT | 7-25s | 7-25s | 含用户说话时间 |
| LLM 推理 | 2-8s | 2-8s | - |
| TTS + 播放 | 2-8s | 2-8s | 网络依赖 |
| **总计** | **28-86s** | **18-61s** | |

## 目标

1. **消除挂起风险**：所有外部调用（`torch.hub.load`、edge_tts）加上超时机制
2. **建立反馈体系**：在模型加载、VAD、STT、TTS 等关键节点推送状态事件，通过 TauriPlatform 广播到 GUI
3. **减少冗余转录**：消除双重转录、去除冗余 VAD
4. **优化 STT 参数**：降低 `beam_size`、研究 tiny 模型可行性

## 范围

### 包含
- `platforms/voice/audio.py`：torch.hub.load 超时、VAD 进度事件
- `platforms/voice/stt.py`：beam_size 优化、去除冗余 VAD、进度回调
- `platforms/voice/wake.py`：合并唤醒+指令转录为单次、超时处理
- `platforms/voice/platform.py`：状态广播、忙等优化
- `gateway/events.py`：新增语音平台状态事件类型
- `config/configs.py`：新增配置项（超时、beam_size 等）

### 不包含
- Whisper 模型替换（保持 faster-whisper）
- TTS 方案替换（保持 edge-tts）
- GPU 加速
- 新硬件支持

## 非目标
- 不改变 VoicePlatform 对外接口（`receive/send` 保持不变）
- 不改变协议接口（Protocol 定义不变）
```

## openspec/changes/voice-platform-full-diag/design.md

- Source: openspec/changes/voice-platform-full-diag/design.md
- Lines: 1-186
- SHA256: 6a60a3a8701bf4640086ec8c99f11153230c9ced50c93b43f7301d44f670e413

[TRUNCATED]

```md
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
```

Full source: openspec/changes/voice-platform-full-diag/design.md

## openspec/changes/voice-platform-full-diag/tasks.md

- Source: openspec/changes/voice-platform-full-diag/tasks.md
- Lines: 1-56
- SHA256: 3f702a85f34c43f4b17d2005e66f871f7301843c54758987c0625f5e58b4c801

```md
# Tasks — Voice Platform Full-Chain Fix

## P0: 消除挂起 + 建立反馈

- [ ] **Task 1**: `torch.hub.load()` 超时保护
  - 在 `SileroAudioIO.record_utterance()` 外层加 `asyncio.wait_for` 超时
  - 超时后降级到 `_record_amplitude_sync()` 振幅 VAD
  - 文件：`platforms/voice/audio.py`
  - 配置项：`voice.silero_download_timeout`

- [ ] **Task 2**: 全链路状态反馈体系
  - 各组件添加 `status_callback` / `_broadcast_status` 机制
  - 关键节点广播：loading → listening → transcribing → thinking → speaking → idle
  - 文件：`platforms/voice/platform.py`、`audio.py`、`stt.py`、`wake.py`
  - 新增事件类型：`gateway/events.py`

## P1: 减少冗余转录 + STT 优化

- [ ] **Task 3**: 唤醒词 + 指令智能分离
  - 在 `TwoStageWakeWord.wait_for_wake()` 中实现唤醒词后指令提取
  - 一次转录同时拿到唤醒确认 + 指令内容
  - 文件：`platforms/voice/wake.py`

- [ ] **Task 4**: STT 参数优化
  - `vad_filter: True → False`（Silero VAD 已过滤）
  - `beam_size: 5 → 3`（CPU 小模型性价比）
  - 文件：`platforms/voice/stt.py`

- [ ] **Task 5**: 静默监听超时与反馈
  - `record_utterance()` 中增加可取消/超时逻辑
  - 超时后广播状态（"超时，重新监听"）
  - 文件：`platforms/voice/audio.py`、`wake.py`

## P2: 忙等优化 + 配置化

- [ ] **Task 6**: 忙等改事件驱动
  - `while self._speaking: sleep()` → `asyncio.Event`
  - 文件：`platforms/voice/platform.py`

- [ ] **Task 7**: 新增 VoiceConfig 配置项
  - `stt_beam_size`、`stt_vad_filter`、`silero_download_timeout`、`stt_model_warmup`、`status_verbose`
  - 文件：`config/configs.py`、`config.yaml`

## P3: 测试与验证

- [ ] **Task 8**: 单元测试更新
  - 测试超时降级逻辑
  - 测试智能指令分离
  - 测试状态事件广播
  - 文件：`tests/test_voice_platform.py`

- [ ] **Task 9**: 集成验证
  - 运行 `python ultimate.py gateway` 验证全链路
  - 冷启动时间可接受（有进度反馈）
  - 热启动交互延迟 < 20s
  - 网络断开时不会永久挂起
```

