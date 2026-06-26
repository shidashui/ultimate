# TTS Network Connection Retry

## 问题

EdgeTTS 网络连接失败时直接抛 `TTSException`，无重试机制，用户收到的回复被丢弃（静默失败）。

```
ERROR tts.py:45 TTS synthesis failed: Cannot connect to host speech.platform.bing.com:443 ssl:...
ERROR platform.py:134 TTS send error: TTS synthesis failed: ...
```

## 根因

`EdgeTTS.synthesize()` 中的 `communicate.stream()` 是单次网络调用，连接失败时立即抛异常，无重试。`VoicePlatform._speak()` 捕获后只记录日志，用户既听不到回复也不知道发生了什么。

## 修复

1. `EdgeTTS.synthesize()` 增加自动重试（最多 3 次，指数退避）
2. 全部重试失败后广播 error 状态事件
3. 新增 `tts_retry_count` 配置项

## 范围

- `platforms/voice/tts.py` — 重试逻辑
- `platforms/voice/platform.py` — 失败广播
- `config/configs.py` — 新配置项
- `config.yaml` — 新配置项
