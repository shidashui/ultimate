# voice-tts-edge

edge-tts adapter for text-to-speech synthesis using Microsoft Edge TTS service.

## ADDED Requirements

### Requirement: edge-tts async synthesis

The TTS module SHALL use `edge_tts` for speech synthesis. Synthesis SHALL be asynchronous and SHALL NOT block the asyncio event loop.

#### Scenario: Synthesize Chinese text to audio

- **GIVEN** a TTS instance configured with voice "zh-CN-XiaoxiaoNeural"
- **WHEN** `await tts.synthesize("你好世界")` is called
- **THEN** MP3 audio bytes are returned
- **AND** the audio is playable via sounddevice

#### Scenario: Graceful failure on network error

- **GIVEN** edge-tts service is unreachable (network down)
- **WHEN** `await tts.synthesize("hello")` is called
- **THEN** an error is logged
- **AND** a TTSException is raised with a descriptive message

### Requirement: Voice selection from config

The TTS voice identifier SHALL be read from `config.yaml` `voice.tts_voice` with a default of `zh-CN-XiaoxiaoNeural`.

#### Scenario: Custom voice from config

- **GIVEN** config.yaml voice.tts_voice = "zh-CN-YunxiNeural"
- **WHEN** TTS is initialized
- **THEN** the Yunxi voice is used for synthesis
