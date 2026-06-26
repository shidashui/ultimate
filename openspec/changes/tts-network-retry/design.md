# TTS Network Retry — Design

## 修复方案

在 `EdgeTTS.synthesize()` 内实现自动重试，使用 `asyncio.sleep` 指数退避。

## 实现

```python
async def synthesize(self, text: str) -> bytes:
    if not text.strip():
        return b""

    max_retries = get_config().voice.tts_retry_count
    last_error = None

    for attempt in range(max_retries + 1):
        try:
            from edge_tts import Communicate
            communicate = Communicate(text, self.voice)
            mp3_data = io.BytesIO()
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    mp3_data.write(chunk["data"])
            result = mp3_data.getvalue()
            if not result:
                logger.warning("TTS produced empty audio for: %s", text[:50])
            return result
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                wait = 2 ** attempt  # 1s, 2s, 4s
                logger.warning("TTS attempt %d/%d failed, retrying in %ds: %s",
                               attempt + 1, max_retries + 1, wait, e)
                await asyncio.sleep(wait)
            else:
                logger.error("TTS all %d attempts failed: %s", max_retries + 1, e)

    raise TTSException(f"TTS synthesis failed after {max_retries + 1} attempts: {last_error}") from last_error
```

## VoicePlatform 侧

`_speak()` 捕获 `TTSException` 后广播 error 状态：

```python
except TTSException as e:
    logger.error("TTS send error: %s", e)
    await self._broadcast_status("error", "语音合成失败，请稍后重试")
```

## 新增配置项

```yaml
voice:
  tts_retry_count: 3  # 最大重试次数（不含首次）
```

## 文件变更

| 文件 | 变更 |
|------|------|
| `platforms/voice/tts.py` | 重试逻辑 |
| `platforms/voice/platform.py` | error 广播 |
| `config/configs.py` | `VoiceConfig.tts_retry_count` |
| `config.yaml` | `tts_retry_count: 3` |
