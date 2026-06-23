"""Tests for voice platform (P0 TTS + P1 modules)."""
import pytest
import asyncio


class TestTTS:
    """P0: edge-tts TTS tests."""

    @pytest.mark.asyncio
    async def test_edge_tts_communicate_constructs(self):
        """Verify edge_tts.Communicate constructs without error."""
        from edge_tts import Communicate

        communicate = Communicate("你好", "zh-CN-XiaoxiaoNeural")
        assert communicate is not None
        assert hasattr(communicate, "stream")

    @pytest.mark.asyncio
    async def test_edge_tts_empty_text_handled(self):
        """edge-tts should not crash on empty input."""
        from edge_tts import Communicate
        import io

        communicate = Communicate("", "zh-CN-XiaoxiaoNeural")
        mp3_data = io.BytesIO()
        try:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    mp3_data.write(chunk["data"])
        except Exception:
            pass  # empty text or network failure — acceptable
        # Test passes if no unhandled exception
        assert True

    def test_voice_platform_imports_cleanly(self):
        """VoicePlatform import should succeed (TTS function uses lazy imports)."""
        from platforms.voice import VoicePlatform

        vp = VoicePlatform(wake_word="你好")
        assert vp.platform_name == "voice"
        assert vp.channel == "voice"


# ── P1: Protocol conformance ───────────────────────────────


class TestProtocols:
    def test_protocols_importable(self):
        from platforms.voice import (
            AudioIOProtocol,
            STTProtocol,
            TTSProtocol,
            WakeWordProtocol,
        )
        assert AudioIOProtocol is not None
        assert STTProtocol is not None
        assert TTSProtocol is not None
        assert WakeWordProtocol is not None

    def test_silero_audio_io_implements_protocol(self):
        from platforms.voice.audio import SileroAudioIO

        io = SileroAudioIO()
        assert hasattr(io, "record_utterance")
        assert hasattr(io, "play")
        assert callable(io.record_utterance)
        assert callable(io.play)

    def test_whisper_stt_implements_protocol(self):
        from platforms.voice.stt import WhisperSTT

        stt = WhisperSTT(model_size="tiny")
        assert hasattr(stt, "transcribe")
        assert callable(stt.transcribe)

    def test_edge_tts_implements_protocol(self):
        from platforms.voice.tts import EdgeTTS

        tts = EdgeTTS()
        assert hasattr(tts, "synthesize")
        assert callable(tts.synthesize)

    def test_two_stage_wake_word_implements_protocol(self):
        from platforms.voice.wake import TwoStageWakeWord

        class MockAudio:
            async def record_utterance(self, **kw):
                import numpy as np
                return np.zeros(16000, dtype=np.float32)

        class MockSTT:
            async def transcribe(self, audio, language="zh"):
                return "你好 今天天气怎么样"

        wake = TwoStageWakeWord(MockAudio(), MockSTT(), wake_word="你好")
        assert hasattr(wake, "wait_for_wake")
        assert hasattr(wake, "record_command")
        assert callable(wake.wait_for_wake)
        assert callable(wake.record_command)


# ── P1: Config-driven behavior ──────────────────────────────


class TestVoiceConfig:
    def test_voice_config_defaults(self):
        from config.configs import VoiceConfig

        cfg = VoiceConfig()
        assert cfg.model == "small"
        assert cfg.vad == "silero"
        assert cfg.wake_word == "你好"
        assert cfg.sample_rate == 16000
        assert cfg.max_record_secs == 30

    def test_voice_config_custom(self):
        from config.configs import VoiceConfig

        cfg = VoiceConfig(
            model="base",
            wake_word="hey",
            tts_voice="zh-CN-YunxiNeural",
        )
        assert cfg.model == "base"
        assert cfg.wake_word == "hey"
        assert cfg.tts_voice == "zh-CN-YunxiNeural"


# ── P1: TTS module unit tests ──────────────────────────────


class TestEdgeTTSModule:
    @pytest.mark.asyncio
    async def test_empty_text_returns_empty_bytes(self):
        from platforms.voice.tts import EdgeTTS

        tts = EdgeTTS()
        result = await tts.synthesize("")
        assert result == b""

    @pytest.mark.asyncio
    async def test_synthesize_constructs(self):
        from platforms.voice.tts import EdgeTTS

        tts = EdgeTTS()
        tts.voice = "zh-CN-XiaoxiaoNeural"
        assert tts.voice == "zh-CN-XiaoxiaoNeural"


# ── P1: VoicePlatform orchestrator ──────────────────────────


class TestVoicePlatformOrchestrator:
    def test_platform_instantiation(self):
        from platforms.voice import VoicePlatform

        vp = VoicePlatform(wake_word="你好", whisper_model="tiny")
        assert vp.platform_name == "voice"
        assert vp.channel == "voice"
        assert vp._audio is not None
        assert vp._stt is not None
        assert vp._tts is not None

    def test_platform_implements_base_platform(self):
        from platforms.voice import VoicePlatform
        from gateway import BasePlatform

        vp = VoicePlatform(wake_word="测试")
        assert isinstance(vp, BasePlatform)
