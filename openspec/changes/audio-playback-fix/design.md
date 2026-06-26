# Audio Playback Fix — Design

## 修复

### 1. 添加 soundfile 依赖

```diff
# requirements.txt
  pyyaml>=6.0
  anthropic
  rich
  prompt_toolkit
+ soundfile
```

### 2. 播放失败时通知用户

`SileroAudioIO._play_sync` 添加 status_callback 引用，异常时广播 error：

```python
@staticmethod
def _play_sync(audio_bytes, sample_rate, status_callback=None):
    try:
        import soundfile as sf
        audio, sr = sf.read(io.BytesIO(audio_bytes))
        sd.play(audio, sr)
        sd.wait()
    except ImportError:
        logger.error("soundfile not installed — run: pip install soundfile")
        raise  # 让上层处理
    except Exception as e:
        logger.error(f"Playback error: {e}")
        raise
```

### 3. VoicePlatform._speak 捕获播放异常

在 `_speak()` 中捕获 `_play_sync` 抛出的异常，广播 error 状态。

## 文件变更

| 文件 | 变更 |
|------|------|
| `requirements.txt` | 添加 `soundfile` |
| `platforms/voice/audio.py` | `_play_sync` 改进错误处理 |
| `platforms/voice/platform.py` | `_speak()` 捕获播放异常 |
