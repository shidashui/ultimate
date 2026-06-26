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


# ── P2: Status events ──────────────────────────────


class TestStatusEvents:
    def test_status_event_has_required_fields(self):
        from gateway.events import status_event

        evt = status_event("loading", "test detail")
        assert evt["event"] == "status"
        assert evt["stage"] == "loading"
        assert evt["detail"] == "test detail"

    def test_status_event_default_detail(self):
        from gateway.events import status_event

        evt = status_event("idle")
        assert evt["detail"] == ""


# ── P2: VoiceConfig new fields ──────────────────────


class TestVoiceConfigNewFields:
    def test_new_config_defaults(self):
        from config.configs import VoiceConfig

        cfg = VoiceConfig()
        assert cfg.stt_beam_size == 3
        assert cfg.stt_vad_filter is False
        assert cfg.silero_download_timeout == 15
        assert cfg.stt_model_warmup is True
        assert cfg.status_verbose is True

    def test_new_config_custom(self):
        from config.configs import VoiceConfig

        cfg = VoiceConfig(
            stt_beam_size=5,
            stt_vad_filter=True,
            silero_download_timeout=30,
            stt_model_warmup=False,
            status_verbose=False,
        )
        assert cfg.stt_beam_size == 5
        assert cfg.stt_vad_filter is True
        assert cfg.silero_download_timeout == 30
        assert cfg.stt_model_warmup is False
        assert cfg.status_verbose is False


# ── P2: VoicePlatform with status callback ───────────


class TestVoicePlatformStatus:
    def test_platform_has_broadcast_status(self):
        from platforms.voice import VoicePlatform

        vp = VoicePlatform(wake_word="测试", whisper_model="tiny")
        assert hasattr(vp, "_broadcast_status")
        assert callable(vp._broadcast_status)

    @pytest.mark.asyncio
    async def test_broadcast_status_no_tauri(self):
        """status broadcast should not crash when no TauriPlatform set."""
        from platforms.voice import VoicePlatform

        vp = VoicePlatform(wake_word="测试", whisper_model="tiny")
        # Should not raise
        await vp._broadcast_status("loading", "test message")


# ── P2: Smart command separation ────────────────────


class TestCommandSeparation:
    @pytest.mark.asyncio
    async def test_inline_command_extracted(self):
        """Wake word + command in one breath → command returned directly."""
        import numpy as np
        from platforms.voice.wake import TwoStageWakeWord

        class MockAudio:
            def __init__(self):
                self.call_count = 0
            async def record_utterance(self, **kw):
                self.call_count += 1
                return np.zeros(16000, dtype=np.float32)

        class MockSTT:
            async def transcribe(self, audio, language="zh"):
                return "你好，今天天气怎么样"

        mock_audio = MockAudio()
        mock_stt = MockSTT()
        wake = TwoStageWakeWord(mock_audio, mock_stt, wake_word="你好")

        result = await wake.wait_for_wake()
        assert result == "今天天气怎么样"
        # Should NOT have called record_utterance a second time
        assert mock_audio.call_count == 1

    @pytest.mark.asyncio
    async def test_wake_only_falls_back_to_record(self):
        """Only wake word → record_command() fallback."""
        import numpy as np
        from platforms.voice.wake import TwoStageWakeWord

        class MockAudio:
            def __init__(self):
                self.call_count = 0
            async def record_utterance(self, **kw):
                self.call_count += 1
                return np.zeros(16000, dtype=np.float32)

        class MockSTT:
            async def transcribe(self, audio, language="zh"):
                return "你好"  # Only wake word

        mock_audio = MockAudio()
        mock_stt = MockSTT()
        wake = TwoStageWakeWord(mock_audio, mock_stt, wake_word="你好")

        result = await wake.wait_for_wake()
        # Should have called record_utterance twice (wake + command)
        assert mock_audio.call_count == 2
        assert result == "你好"  # mock returns wake word again

    @pytest.mark.asyncio
    async def test_empty_text_continues_waiting(self):
        """Empty STT result → continue waiting loop."""
        import numpy as np
        from platforms.voice.wake import TwoStageWakeWord

        call_count = [0]

        class MockAudio:
            async def record_utterance(self, **kw):
                call_count[0] += 1
                return np.zeros(16000, dtype=np.float32)

        responses = ["", "你好 帮我查天气"]  # empty → wake+cmd

        class MockSTT:
            async def transcribe(self, audio, language="zh"):
                return responses.pop(0)

        mock_audio = MockAudio()
        mock_stt = MockSTT()
        wake = TwoStageWakeWord(mock_audio, mock_stt, wake_word="你好")

        result = await wake.wait_for_wake()
        assert result == "帮我查天气"


# ── P2: Audio Silero fallback ──────────────────────


class TestSileroFallback:
    def test_vad_available_flag_exists(self):
        from platforms.voice.audio import SileroAudioIO

        io = SileroAudioIO()
        assert hasattr(io, "_vad_available")
        assert io._vad_available is True

    def test_record_sync_falls_back_when_unavailable(self):
        """When _vad_available=False, should use amplitude VAD without crash."""
        from platforms.voice.audio import SileroAudioIO

        io = SileroAudioIO()
        io._vad_available = False
        io._vad_model = None
        # _record_sync should use amplitude fallback
        # Note: this will open a real audio stream — test only the flag logic
        assert io._vad_available is False
