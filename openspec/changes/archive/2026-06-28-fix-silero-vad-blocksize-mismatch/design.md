# Design: Fix Silero VAD Blocksize Mismatch

## Problem

`blocksize=0` lets WASAPI auto-negotiate to 640 samples (40ms), but Silero VAD requires exactly 512 samples at 16000Hz. `stream.read(FRAME_SIZE)` with `FRAME_SIZE=512` returns 640 samples, crashing the model.

## Solution

Decouple audio read size from VAD input size:

1. Keep `blocksize=0` for WASAPI compatibility
2. Accumulate reads into a float32 sample buffer
3. Extract exactly 512-sample slices from the buffer for VAD
4. Track audio frames aligned with VAD processing

### Key change: `_record_silero_sync` (audio.py:100-148)

- Add a `sample_acc` accumulator buffer
- After each `stream.read(FRAME_SIZE)`, concatenate into `sample_acc`
- Loop: while `len(sample_acc) >= FRAME_SIZE`, extract 512 samples, run VAD, advance
- Store audio as float32 arrays per VAD frame (simplifies final reconstruction)

No interface changes. No new dependencies. Single file touched.
