# Audio Playback — Missing soundfile Dependency

## 问题

```
[Voice] speaking: 正在合成语音…
ERROR audio.py:203 Playback error: No module named 'soundfile'
```

`soundfile` 未安装且未在 `requirements.txt` 中声明。`_play_sync` 静默捕获异常只记日志，用户听不到任何回复。

## 根因

1. `soundfile` 不在 `requirements.txt` 中，`pip install -r requirements.txt` 不会安装
2. `_play_sync` 的 `except Exception` 只写日志不通知用户

## 修复

1. `requirements.txt` 添加 `soundfile`
2. `_play_sync` 异常时广播 error 状态

## 范围

- `requirements.txt` — 添加依赖
- `platforms/voice/audio.py` — 错误广播
