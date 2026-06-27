# Tasks: Fix Silero VAD Blocksize Mismatch

- [x] Add sample accumulator buffer to `_record_silero_sync` to decouple read size from VAD input size
- [x] Run voice-related tests to confirm fix
