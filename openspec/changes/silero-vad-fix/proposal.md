# Silero VAD — Missing torchaudio Dependency

## 问题

```
WARNING audio.py:65 Silero VAD warmup failed: No module named 'torchaudio', falling back to amplitude VAD
```

`torchaudio` 未安装且未在 requirements.txt 声明。Silero VAD 依赖 torchaudio 做音频处理，缺失时降级到振幅 VAD（精度低、易误触发）。

## 修复

1. `requirements.txt` 添加 `torchaudio`

## 范围

- `requirements.txt` — 单文件
