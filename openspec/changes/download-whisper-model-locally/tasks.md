# Tasks: download-whisper-model-locally

## Task 1: 添加 `huggingface-hub` 依赖

- [x] 将 `huggingface-hub` 添加到 `requirements.txt`
- [x] 确保依赖版本兼容

## Task 2: 创建模型下载脚本 `scripts/download-whisper-model.py`

- [x] 使用 `huggingface_hub.snapshot_download` 下载模型到 `models/whisper/<model_size>/`
- [x] 支持 `--model` 参数指定模型大小（默认 `small`）
- [x] 支持 `--check` 参数验证本地模型完整性
- [x] 显示下载进度条
- [x] 下载完成后写入 `.model_ready` 标记文件
- [x] 确保 `models/whisper/` 目录存在

## Task 3: 修改 `stt.py` 支持本地模型路径

- [x] `_get_model()` 中优先检测 `models/whisper/<model_size>/` 是否存在
- [x] 存在则用本地路径，不存在回退到模型 size 名称（原行为）
- [x] 日志输出模型加载来源（本地/HuggingFace）

## Task 4: 配置 `.gitignore` 排除模型文件

- [x] 在 `.gitignore` 中添加 `models/whisper/*` 排除模型大文件
- [x] 保留 `models/whisper/.gitkeep`

## 验证标准

- [ ] `python scripts/download-whisper-model.py --model tiny` 成功下载模型
- [ ] 再次运行 `--check` 验证完整
- [ ] `stt.py` 从本地路径加载模型成功，日志输出 "本地模型"
- [ ] `WhisperSTT.warmup()` 显著加速（< 2s 而非网络下载数十秒）
