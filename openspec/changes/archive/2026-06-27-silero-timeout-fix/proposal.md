# Silero VAD Warmup Timeout

## 问题

```
WARNING Silero VAD warmup timed out, falling back to amplitude VAD
[Voice] loading: 语音检测模型超时，降级到振幅检测
```

`silero_download_timeout` 默认 15s 对于首次从 GitHub 下载 ~45MB Silero 模型来说太短。

## 修复

`VoiceConfig.silero_download_timeout` 默认值 15 → 60，`config.yaml` 同步更新。

## 范围

- `config/configs.py`
- `config.yaml`
