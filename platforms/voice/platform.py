"""VoicePlatform — orchestrator assembling AudioIO/STT/TTS/WakeWord modules."""
from __future__ import annotations

import asyncio
import logging

from gateway import BasePlatform, Message, Reply
from config.configs import get_config
from platforms.voice.audio import SileroAudioIO
from platforms.voice.stt import WhisperSTT
from platforms.voice.tts import EdgeTTS, TTSException
from platforms.voice.wake import TwoStageWakeWord
from gateway.events import (
    wake_event, stt_event, text_chunk_event,
    tts_start_event, tts_end_event, idle_event, status_event,
)

logger = logging.getLogger(__name__)

VOICE_USER_ID = "voice_user"
VOICE_SESSION_ID = "voice_default"


class VoicePlatform(BasePlatform):
    """Modular voice platform — config-driven, dependency-injected components."""

    platform_name = "voice"
    channel = "voice"

    def __init__(self, wake_word: str | None = None, whisper_model: str | None = None):
        cfg = get_config().voice
        self._wake_word = wake_word or cfg.wake_word
        self._model_size = whisper_model or cfg.model
        self._verbose = cfg.status_verbose

        # Components (created at init, started in start())
        self._audio = SileroAudioIO(status_callback=self._broadcast_status)
        self._stt = WhisperSTT(
            model_size=self._model_size,
            status_callback=self._broadcast_status,
        )
        self._tts = EdgeTTS()
        self._wake: TwoStageWakeWord | None = None

        self._queue: asyncio.Queue = asyncio.Queue()
        self._speaking: bool = False
        self._speak_done: asyncio.Event = asyncio.Event()
        self._speak_done.set()  # not speaking initially
        self._tauri_platform = None

    # ── Tauri GUI 集成 ───────────────────────────────────

    def set_tauri_platform(self, tauri_platform) -> None:
        """设置 TauriPlatform 引用，用于 GUI 事件广播。"""
        self._tauri_platform = tauri_platform

    async def _broadcast(self, event: dict) -> None:
        """向 Tauri GUI 广播事件。"""
        if self._tauri_platform:
            await self._tauri_platform.broadcast(event)

    async def _broadcast_status(self, stage: str, detail: str = "") -> None:
        """统一状态广播：推送到 Tauri GUI + 终端输出。"""
        if self._tauri_platform:
            try:
                await self._tauri_platform.broadcast(status_event(stage, detail))
            except Exception:
                logger.debug("status broadcast error", exc_info=True)
        if self._verbose:
            print(f"[Voice] {stage}: {detail}", flush=True)

    def get_text_chunk_callback(self):
        """返回 on_text_chunk 回调，供 Gateway/AgentRunner 流式推送。"""
        if self._tauri_platform is None:
            return None
        return lambda text: asyncio.create_task(
            self._broadcast(text_chunk_event(text))
        )

    # ── Lifecycle ───────────────────────────────────────

    async def start(self) -> None:
        logger.info(
            "voice platform starting (model=%s, wake_word=%s, tts=%s)",
            self._model_size, self._wake_word, get_config().voice.tts_voice,
        )

        cfg = get_config().voice

        # ── Warmup phase ──
        await self._broadcast_status("loading", "正在加载语音模型…")

        if cfg.stt_model_warmup:
            # Parallel warmup for Whisper + Silero
            results = await asyncio.gather(
                self._stt.warmup(timeout=60.0),
                self._audio.warmup_silero(timeout=float(cfg.silero_download_timeout)),
                return_exceptions=True,
            )
            whisper_ok = results[0] if not isinstance(results[0], Exception) else False
            silero_ok = results[1] if not isinstance(results[1], Exception) else False

            if not whisper_ok:
                logger.error("Whisper model warmup failed — voice platform may not function")
                await self._broadcast_status("error", "Whisper模型加载失败")
        else:
            # Legacy: warm STT model inline
            _ = self._stt._get_model()
            logger.info("Whisper model '%s' loaded", self._model_size)

        self._wake = TwoStageWakeWord(
            audio_io=self._audio,
            stt=self._stt,
            wake_word=self._wake_word,
            status_callback=self._broadcast_status,
        )
        asyncio.create_task(self._listen_loop())

    async def stop(self) -> None:
        logger.info("voice platform stopped")

    # ── BasePlatform interface ───────────────────────────

    async def receive(self) -> Message:
        return await self._queue.get()

    async def send(self, reply: Reply) -> None:
        text = reply.content.strip()
        if not text:
            return
        try:
            await self._speak(text)
        except TTSException as e:
            logger.error("TTS send error: %s", e)
            await self._broadcast_status("error", "语音合成失败，请稍后重试")
        finally:
            # 交互完成，广播 idle
            await self._broadcast(idle_event())
            await self._broadcast_status("idle", "就绪")

    # ── Listen loop ─────────────────────────────────────

    async def _listen_loop(self) -> None:
        logger.info("listen loop started")

        while True:
            try:
                # Wait for TTS to finish before listening (event-driven)
                await self._speak_done.wait()

                # Wake word → record command
                text = await self._wake.wait_for_wake()
                if text:
                    # 唤醒 → 推 wake + stt 事件
                    await self._broadcast(wake_event())
                    await self._broadcast(stt_event(text))
                    await self._broadcast_status("thinking", "正在思考…")

                    await self._queue.put(Message(
                        platform=self.platform_name,
                        user_id=VOICE_USER_ID,
                        session_id=VOICE_SESSION_ID,
                        content=text,
                    ))

            except Exception as e:
                logger.error("Listen loop error: %s", e)
                await asyncio.sleep(1)

    # ── TTS ─────────────────────────────────────────────

    async def _speak(self, text: str) -> None:
        self._speaking = True
        self._speak_done.clear()
        await self._broadcast(tts_start_event())
        await self._broadcast_status("speaking", "正在合成语音…")
        try:
            mp3_bytes = await self._tts.synthesize(text)
            if mp3_bytes:
                await self._audio.play(mp3_bytes)
        except Exception as e:
            logger.error("TTS/playback error: %s", e)
            await self._broadcast_status("error", "语音播报失败，请检查音频设备")
        finally:
            await self._broadcast(tts_end_event())
            self._speaking = False
            self._speak_done.set()
