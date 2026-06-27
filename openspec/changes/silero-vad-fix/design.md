# Silero VAD Fix — Design

## 修复

`requirements.txt` 添加 `torchaudio` 依赖声明。

`torch.hub.load("snakers4/silero-vad")` 加载的 Silero VAD 模型内部使用 `torchaudio` 进行音频重采样和特征提取。缺失时模型加载失败，`warmup_silero()` 捕获异常后降级到振幅 VAD。

安装 `torchaudio` 后 Silero VAD 正常加载，语音检测精度显著提升。
