## Why

Whisper 模型（faster-whisper）每次首次启动时从 HuggingFace 下载或校验缓存，网络慢时导致加载耗时数十秒甚至超时。将模型预下载到项目目录下，可避免运行时网络依赖，显著加速启动。

## What Changes

- 新增 `scripts/download-whisper-model.py`：一键下载指定 Whisper 模型到 `models/whisper/` 目录
- 修改 `platforms/voice/stt.py`：`WhisperModel` 初始化时优先使用本地模型路径 `models/whisper/<size>/`
- 新增 `models/whisper/.gitkeep`：占位目录

## Capabilities

### New Capabilities
- `whisper-model-local`: 本地预下载 Whisper 模型，消除运行时网络依赖

### Modified Capabilities
<!-- 无 spec 级需求变更 -->

## Impact

- `platforms/voice/stt.py` — 修改模型加载路径
- `scripts/download-whisper-model.py` — 新增下载脚本
- `models/whisper/` — 新增模型存放目录
- 新增依赖：`huggingface-hub`（或使用 faster-whisper 自带的下载能力）
- `.gitignore` — 确保模型文件（大文件）不被 git 跟踪
