# Proposal: Strip Markdown Before TTS

## Why

TTS 引擎会逐字朗读 LLM 返回的 markdown 格式文本，导致 `**bold**`、`# heading`、`[link](url)`、代码块等符号被语音读出，严重影响听觉体验。

## What Changes

- 在 `EdgeTTS.synthesize()` 中，将文本送入 TTS 引擎前先剥离 markdown 语法，转为纯文本

## Capabilities

### Modified Capabilities
- None — implementation bugfix only, no requirement changes

## Impact

- [platforms/voice/tts.py](platforms/voice/tts.py) — `synthesize` 方法
