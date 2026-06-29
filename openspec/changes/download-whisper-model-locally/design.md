## Context

当前 `faster-whisper` 的 `WhisperModel(model_size)` 默认从 HuggingFace Hub 下载模型。
首次启动时若网络慢，下载耗时可达数十秒，导致 `warmup()` 超时返回 `False`。

`faster-whisper` 的 `WhisperModel` 构造函数 `model_size_or_path` 参数既接受 size 名字（`"small"`、`"medium"`），
也接受本地目录路径。若本地目录已有完整模型文件，直接加载即可，无需联网。

当前项目 `config.yaml` 中 `voice.model: small`，加载的是 `small` 模型（~461MB）。

## Goals / Non-Goals

**Goals:**
- 提供脚本一键下载 Whisper 模型到项目 `models/whisper/` 目录
- `stt.py` 优先从本地路径加载模型，不存在时回退到 HuggingFace 下载（容错）
- 大幅缩短首次模型加载时间

**Non-Goals:**
- 不修改模型推理逻辑
- 不替换 `faster-whisper` 库
- 不做模型量化或格式转换（保持原有 `int8` 计算类型）

## Decisions

| 决策 | 选择 | 理由 |
|------|------|------|
| 下载工具 | `huggingface_hub` CLI（`snapshot_download`） | faster-whisper 的模型存储在 HuggingFace，`huggingface_hub` 是官方下载工具，支持断点续传、进度条 |
| 本地路径 | `models/whisper/{model_size}/` | 约定优于配置，路径直观；与项目根目录一致，便于打包分发 |
| 加载策略 | 先判断本地路径是否存在，存在则用本地路径 | 不破坏原有回退逻辑，本地没有时仍然走 HuggingFace（兼容现有行为和 CI 环境） |
| 模型文件 git 管理 | 加入 `.gitignore`，不跟踪大文件 | Whisper small 约 461MB，不适合 git 版本管理；用户通过脚本按需下载 |

### 详细流程

1. 用户运行 `python scripts/download-whisper-model.py`（支持 `--model small` 参数）
2. 脚本使用 `huggingface_hub.snapshot_download` 下载 `Systran/faster-whisper-small`（或对应模型）到 `models/whisper/small/`
3. `stt.py._get_model()` 检测 `models/whisper/small/` 是否存在 → 存在则用本地路径，不存在用原来的 `model_size` 字符串
4. 下载脚本同时写入一个 `.model_ready` 标记文件，方便其他组件检测

## Risks / Trade-offs

| 风险 | 缓解措施 |
|------|----------|
| 模型文件大（small ~461MB），下载耗流量 | 脚本支持 `--model` 参数选 small/tiny 等；输出下载进度 |
| `huggingface_hub` 额外依赖 | 将其添加到 `requirements.txt` |
| 本地模型被误删 | 脚本提供 `--check` 模式验证模型完整性，缺失自动重下 |
