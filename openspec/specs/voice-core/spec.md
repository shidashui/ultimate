# voice-core

Voice platform core module interfaces and configuration-driven architecture.

## ADDED Requirements

### Requirement: Voice platform modular decomposition

The voice platform SHALL be decomposed into four independent modules with protocol interfaces:
- **AudioIOProtocol** — audio capture and playback
- **STTProtocol** — speech-to-text transcription
- **TTSProtocol** — text-to-speech synthesis
- **WakeWordProtocol** — wake word detection

Each module SHALL be independently testable via dependency injection. VoicePlatform SHALL act only as the orchestrator that assembles modules and drives the listen→transcribe→reply→speak lifecycle.

#### Scenario: Module replaces backend independently

- **GIVEN** a VoicePlatform configured with STT backed by faster-whisper
- **WHEN** the STT backend is changed to Sherpa-ONNX
- **THEN** no other module (AudioIO, TTS, WakeWord) requires modification
- **AND** the platform continues to function identically

#### Scenario: Module tested with mock dependency

- **GIVEN** a STTProtocol implementation
- **WHEN** a test injects a pre-recorded audio sample
- **THEN** the STT module transcribes it without requiring actual microphone hardware
- **AND** the test result is deterministic

### Requirement: Voice configuration from config.yaml

Voice platform parameters SHALL be read from `config.yaml` under a `voice:` section, not hardcoded as module-level constants. Parameters include:
- `model`: whisper model size (e.g., `small`, `base`)
- `vad`: VAD backend (`silero`)
- `vad_threshold`: VAD sensitivity (0.0-1.0)
- `wake_word`: wake word phrase
- `sample_rate`: audio sample rate in Hz
- `max_record_secs`: maximum recording duration in seconds
- `tts_voice`: edge-tts voice identifier

#### Scenario: Config changes take effect without code change

- **GIVEN** a running voice platform with wake_word = "你好"
- **WHEN** config.yaml voice.wake_word is changed to "hey" and the platform restarts
- **THEN** the new wake word "hey" is used
- **AND** no Python source file was modified

#### Scenario: Missing config key uses default

- **GIVEN** a config.yaml with voice section omitting `max_record_secs`
- **WHEN** VoiceConfig is loaded
- **THEN** max_record_secs defaults to 30

### Requirement: VAD upgraded to Silero-VAD

Voice Activity Detection SHALL use `silero-vad` (ONNX model) instead of `webrtcvad`. It SHALL output speech probability (0.0-1.0) per frame, enabling confidence-based endpoint decisions.

#### Scenario: Silero VAD detects speech reliably

- **GIVEN** an audio stream containing human speech
- **WHEN** Silero VAD processes the frames
- **THEN** speech probability > 0.5 for speech frames
- **AND** speech probability < 0.5 for silence frames

#### Scenario: VAD endpoint detection stops recording

- **GIVEN** Silero VAD in recording mode with triggered=True
- **WHEN** speech probability drops below threshold for consecutive frames
- **THEN** recording stops and the captured audio segment is returned
- **AND** no trailing silence is included beyond the padding buffer

### Requirement: STT uses in-memory pipeline

Speech-to-text SHALL avoid writing temporary WAV files to disk. Audio data SHALL be passed to faster-whisper via in-memory bytes buffer.

#### Scenario: No temp files created during transcription

- **GIVEN** a numpy audio array
- **WHEN** STT module transcribes it
- **THEN** no .wav file is created in /tmp or the working directory
- **AND** transcription result text is returned

### Requirement: Wake word two-stage detection

Wake word detection SHALL use a two-stage pipeline:
1. Silero VAD endpoint detection identifies candidate speech segments
2. Whisper ASR transcribes the candidate, and substring matching against the configured wake word determines if it was spoken

This replaces the current approach of running full Whisper ASR on every VAD-triggered segment.

#### Scenario: Wake word spoken triggers activation

- **GIVEN** wake_word = "你好" and an audio segment containing "你好，今天天气怎么样"
- **WHEN** the two-stage pipeline runs
- **THEN** Whisper transcribes the segment
- **AND** substring "你好" matches
- **AND** the platform transitions to command listening mode

#### Scenario: Non-wake speech does not trigger

- **GIVEN** wake_word = "你好" and an audio segment containing "没问题"
- **WHEN** the two-stage pipeline runs
- **THEN** the segment is ignored and the platform continues waiting

### Requirement: TTS uses async interface

TTS synthesis SHALL be asynchronous (async/await). The synchronous blocking `pyttsx3` engine SHALL be removed.

#### Scenario: TTS does not block event loop

- **GIVEN** a text string to synthesize
- **WHEN** TTS.synthesize(text) is called
- **THEN** other async tasks continue to execute during synthesis
- **AND** the resulting audio is playable
