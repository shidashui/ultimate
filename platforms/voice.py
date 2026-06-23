# platforms/voice.py
import asyncio
import logging
import tempfile
import os
import collections
import numpy as np
import sounddevice as sd
import webrtcvad
from scipy.io.wavfile import write as wav_write
from faster_whisper import WhisperModel
from gateway import BasePlatform, Message, Reply

logger = logging.getLogger(__name__)

SAMPLE_RATE  = 16000
FRAME_MS     = 20                                    # webrtcvad 要求 10/20/30ms
FRAME_SIZE   = int(SAMPLE_RATE * FRAME_MS / 1000)   # 320 samples
PADDING_MS   = 400                                   # 静音缓冲区时长
NUM_PADDING  = PADDING_MS // FRAME_MS                # 缓冲区帧数 = 20
SPEECH_RATIO = 0.75                                  # 触发开始/结束的语音帧占比
VAD_MODE     = 3                                     # 0-3，越大越激进
MAX_SECS     = 30

VOICE_USER_ID    = "voice_user"
VOICE_SESSION_ID = "voice_default"


class VoicePlatform(BasePlatform):
    platform_name = "voice"
    channel       = "voice"

    def __init__(
        self,
        whisper_model: str = "small",
        wake_word:     str = "你好",
        vad_mode:      int = VAD_MODE,
    ):
        self._whisper_model_size = whisper_model
        self._wake_word          = wake_word.strip()
        self._vad                = webrtcvad.Vad(vad_mode)
        self._model: WhisperModel | None = None
        self._queue: asyncio.Queue       = asyncio.Queue()
        self._speaking: bool             = False

    # ------------------------------------------------------------------ #
    #  生命周期                                                             #
    # ------------------------------------------------------------------ #

    async def start(self) -> None:
        logger.info("voice 平台启动，加载 Whisper 模型…")
        loop = asyncio.get_event_loop()
        self._model = await loop.run_in_executor(
            None,
            lambda: WhisperModel(
                self._whisper_model_size,
                device="cpu",
                compute_type="int8",
            ),
        )
        logger.info(f"Whisper '{self._whisper_model_size}' 加载完成，唤醒词='{self._wake_word}'")
        asyncio.create_task(self._listen_loop())

    async def stop(self) -> None:
        logger.info("voice 平台停止")

    # ------------------------------------------------------------------ #
    #  BasePlatform 接口                                                   #
    # ------------------------------------------------------------------ #

    async def receive(self) -> Message:
        return await self._queue.get()

    async def send(self, reply: Reply) -> None:
        text = reply.content.strip()
        if not text:
            return
        try:
            await self._speak(text)
        except Exception as e:
            logger.error(f"TTS error: {e}")

    # ------------------------------------------------------------------ #
    #  主监听循环                                                           #
    # ------------------------------------------------------------------ #

    async def _listen_loop(self) -> None:
        loop = asyncio.get_event_loop()
        logger.info("监听循环已启动")

        while True:
            try:
                # ① 等待 TTS 播完再监听
                while self._speaking:
                    await asyncio.sleep(0.05)

                # ② 唤醒词检测
                print(f"💤 等待唤醒词「{self._wake_word}」…", flush=True)
                while True:
                    while self._speaking:
                        await asyncio.sleep(0.05)
                    audio = await loop.run_in_executor(None, self._record_utterance)
                    if audio is None:
                        continue
                    text = await loop.run_in_executor(None, self._transcribe, audio)
                    if self._wake_word in text.strip():
                        break

                # ③ 录制指令
                print("✅ 已唤醒，请说指令…", flush=True)
                audio = await loop.run_in_executor(None, self._record_utterance)
                if audio is None:
                    continue

                # ④ 转写入队
                text = (await loop.run_in_executor(None, self._transcribe, audio)).strip()
                if text:
                    logger.info(f"STT: {text}")
                    await self._queue.put(Message(
                        platform   = self.platform_name,
                        user_id    = VOICE_USER_ID,
                        session_id = VOICE_SESSION_ID,
                        content    = text,
                    ))

            except Exception as e:
                logger.error(f"Listen loop error: {e}")
                await asyncio.sleep(1)

    # ------------------------------------------------------------------ #
    #  录音（VAD 驱动）                                                     #
    # ------------------------------------------------------------------ #

    def _record_utterance(self) -> np.ndarray | None:
        """
        webrtcvad 驱动的录音：
          - 滑动窗口语音帧占比 >= SPEECH_RATIO → 开始录制
          - 开始后占比 < (1-SPEECH_RATIO)     → 停止录制
        """
        ring       = collections.deque(maxlen=NUM_PADDING)
        triggered  = False
        pcm_buf: list[bytes] = []
        max_frames = int(MAX_SECS * 1000 / FRAME_MS)

        with sd.RawInputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="int16",
            blocksize=FRAME_SIZE,
        ) as stream:
            for _ in range(max_frames):
                raw, _    = stream.read(FRAME_SIZE)
                pcm       = bytes(raw)
                is_speech = self._vad.is_speech(pcm, SAMPLE_RATE)
                ring.append(is_speech)

                if not triggered:
                    # 预缓冲，保留最近 NUM_PADDING 帧，语音开始时不丢头部
                    pcm_buf.append(pcm)
                    if len(pcm_buf) > NUM_PADDING:
                        pcm_buf.pop(0)
                    if sum(ring) / len(ring) >= SPEECH_RATIO:
                        triggered = True
                        print("🔴 录音中…", flush=True)
                else:
                    pcm_buf.append(pcm)
                    if sum(ring) / len(ring) < (1 - SPEECH_RATIO):
                        print("⏹  录音结束", flush=True)
                        break

        if not triggered:
            return None

        raw_bytes = b"".join(pcm_buf)
        audio = np.frombuffer(raw_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        return audio if len(audio) > SAMPLE_RATE * 0.3 else None

    # ------------------------------------------------------------------ #
    #  语音识别                                                             #
    # ------------------------------------------------------------------ #

    def _transcribe(self, audio: np.ndarray) -> str:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmp = f.name
        try:
            wav_write(tmp, SAMPLE_RATE, (audio * 32768).astype(np.int16))
            segments, _ = self._model.transcribe(
                tmp,
                language       = "zh",
                vad_filter     = True,
                initial_prompt = "以下是普通话日常对话。",
                beam_size      = 5,
            )
            return "".join(s.text for s in segments)
        finally:
            os.unlink(tmp)

    # ------------------------------------------------------------------ #
    #  TTS                                                               #
    # ------------------------------------------------------------------ #

    async def _speak(self, text: str) -> None:
        self._speaking = True
        try:
            import io
            import edge_tts

            voice = "zh-CN-XiaoxiaoNeural"
            communicate = edge_tts.Communicate(text, voice)
            mp3_data = io.BytesIO()
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    mp3_data.write(chunk["data"])
            mp3_bytes = mp3_data.getvalue()

            if mp3_bytes:
                await asyncio.get_event_loop().run_in_executor(
                    None, _play_mp3_sync, mp3_bytes
                )
        except Exception as e:
            logger.error(f"TTS error: {e}")
        finally:
            self._speaking = False


# ------------------------------------------------------------------ #
#  工具函数                                                             #
# ------------------------------------------------------------------ #

def _play_mp3_sync(mp3_bytes: bytes) -> None:
    """Decode MP3 bytes and play via sounddevice (runs in executor)."""
    import io
    import soundfile as sf

    audio, sr = sf.read(io.BytesIO(mp3_bytes))
    sd.play(audio, sr)
    sd.wait()