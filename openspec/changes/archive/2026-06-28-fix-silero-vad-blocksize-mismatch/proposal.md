# Proposal: Fix Silero VAD Blocksize Mismatch

## Why

Silero VAD crash: `blocksize=0` lets PortAudio/WASAPI auto-negotiate to 640 samples (40ms), but the Silero VAD model **requires exactly 512 samples at 16000Hz**. The `stream.read(512)` call returns 640 samples when the auto-negotiated blocksize differs, causing a hard crash with `ValueError: Provided number of samples is 640`.

## What Changes

- Fix `_record_silero_sync` to decouple audio read size from VAD input size: accumulate incoming audio chunks into a buffer, then feed the Silero model exactly 512-sample slices
- Friendlier handling: if the auto-negotiated blocksize returns a different count than expected, log it but continue working by buffering

## Capabilities

### Modified Capabilities
- None — implementation bugfix only, no requirement changes

## Impact

- [platforms/voice/audio.py:100-148](platforms/voice/audio.py) — `_record_silero_sync` method
