# Tasks — Voice Platform Full-Chain Fix

## P0: 消除挂起 + 建立反馈

- [x] **Task 1**: `torch.hub.load()` 超时保护
  - 在 `SileroAudioIO` 中增加 `warmup_silero()` 启动预热方法，带 `asyncio.wait_for` 超时
  - 超时/失败后降级到 `_record_amplitude_sync()` 振幅 VAD
  - 文件：`platforms/voice/audio.py`
  - 配置项：`voice.silero_download_timeout`

- [x] **Task 2**: 全链路状态反馈体系
  - 各组件添加 `status_callback` 参数，VoicePlatform 统一注入 `_broadcast_status`
  - 关键节点广播：loading → listening → transcribing → thinking → speaking → idle
  - 文件：`platforms/voice/platform.py`、`audio.py`、`stt.py`、`wake.py`
  - 新增事件类型：`gateway/events.py` — `status_event()`

## P1: 减少冗余转录 + STT 优化

- [x] **Task 3**: 唤醒词 + 指令智能分离
  - 在 `TwoStageWakeWord.wait_for_wake()` 中实现唤醒词后指令提取
  - 一次转录同时拿到唤醒确认 + 指令内容（仅唤醒词时回退到 8s 二次录音）
  - 文件：`platforms/voice/wake.py`

- [x] **Task 4**: STT 参数优化
  - `vad_filter: True → False`（Silero VAD 已过滤，配置驱动）
  - `beam_size: 5 → 3`（CPU 小模型性价比，配置驱动）
  - 文件：`platforms/voice/stt.py`

- [x] **Task 5**: 静默监听超时与反馈
  - `record_command()` 超时从 30s 缩短到 8s（用户已唤醒）
  - Silent VAD 预热失败后广播降级状态
  - 文件：`platforms/voice/audio.py`、`wake.py`

## P2: 忙等优化 + 配置化

- [x] **Task 6**: 忙等改事件驱动
  - `while self._speaking: sleep()` → `asyncio.Event`
  - 文件：`platforms/voice/platform.py`

- [x] **Task 7**: 新增 VoiceConfig 配置项
  - `stt_beam_size`、`stt_vad_filter`、`silero_download_timeout`、`stt_model_warmup`、`status_verbose`
  - 文件：`config/configs.py`、`config.yaml`

## P3: 测试与验证

- [x] **Task 8**: 单元测试更新
  - Status 事件测试、新配置项测试、智能指令分离测试（3 边界场景）、Silero 降级测试
  - 全部 25/25 通过
  - 文件：`tests/test_voice_platform.py`

- [ ] **Task 9**: 集成验证（需要真实硬件：麦克风 + 扬声器）
  - 运行 `python ultimate.py gateway --no-gui` 验证全链路
  - 冷启动时间可接受（有进度反馈）
  - 热启动交互延迟 < 20s
  - 网络断开时不会永久挂起
