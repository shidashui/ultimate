# Tasks — Audio Playback Fix

- [x] **Task 1**: `requirements.txt` 添加 `soundfile`
  - 文件：`requirements.txt`

- [x] **Task 2**: `_play_sync` 异常改为 raise（不再静默吞掉）
  - 文件：`platforms/voice/audio.py`

- [x] **Task 3**: `_speak()` 捕获播放异常广播 error
  - 文件：`platforms/voice/platform.py`
