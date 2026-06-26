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
