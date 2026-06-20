# platforms/wechat.py
import asyncio
import logging
from pathlib import Path

from platforms.lib.wx_sdk.app.bot import WeixinBot, MediaInfo
from platforms.lib.wx_sdk.app.types import MessageItemType, TypingStatus
from config.configs import WORKDIR

from gateway import BasePlatform, Message, Reply

logger = logging.getLogger(__name__)

MEDIA_SAVE_DIR = WORKDIR / ".weixin-clawbot" / "received_media"


class WeChatPlatform(BasePlatform):
    platform_name = "wechat"
    channel       = "wechat" 

    def __init__(
        self,
        storage_path: str | Path = MEDIA_SAVE_DIR,
        show_typing: bool = False,
    ):
        self.storage_path = Path(storage_path)
        self.show_typing = show_typing

        self._bot = WeixinBot(storage_path=str(self.storage_path))
        self._queue: asyncio.Queue[tuple[Message, object]] = asyncio.Queue()
        # 保存原始 SDK message，用于 send 时拿 context_token / from_user_id
        self._pending: dict[str, object] = {}

        self._register_handlers()

    # ─────────────────────────────────────────────
    # SDK 回调注册
    # ─────────────────────────────────────────────

    def _register_handlers(self) -> None:

        @self._bot.on_status
        async def on_status(msg: str):
            logger.info("[WeChat Status] %s", msg)

        @self._bot.on_error
        async def on_error(error: Exception):
            logger.error("[WeChat Error] %s", error)

        @self._bot.on_message
        async def on_message(raw_msg):
            await self._handle_raw(raw_msg)

    async def _handle_raw(self, raw_msg) -> None:
        """将 SDK 回调转换为 Gateway Message 并入队"""
        text, media_info = await self._bot.process_message(
            raw_msg,
            save_dir=str(self.storage_path),
        )

        # 目前只处理文字消息，媒体消息转成描述文本
        if text is None and media_info is None:
            return

        content = text or self._media_to_text(media_info)

        msg = Message(
            platform=self.platform_name,
            user_id=raw_msg.from_user_id or "",
            session_id=raw_msg.session_id or raw_msg.from_user_id or "",
            content=content,
            raw={
                "context_token": raw_msg.context_token,
                "from_user_id": raw_msg.from_user_id,
                "media_info": media_info,
            },
        )
        # 暂存原始 SDK message，send 时需要 context_token
        self._pending[msg.session_id] = raw_msg

        logger.debug("[WeChat] 入队 user=%s content=%s", msg.user_id, content[:40])
        await self._queue.put(msg)

    @staticmethod
    def _media_to_text(media_info: MediaInfo | None) -> str:
        if not media_info:
            return ""
        type_name = MessageItemType(media_info.type).name
        return f"[{type_name}] {media_info.file_name} ({media_info.file_size} bytes)"

    # ─────────────────────────────────────────────
    # BasePlatform 接口实现
    # ─────────────────────────────────────────────

    async def receive(self) -> Message:
        """Gateway 轮询：阻塞等待下一条消息"""
        return await self._queue.get()

    async def send(self, reply: Reply) -> None:
        """将 LLM 回复通过微信发回给用户"""
        raw_msg = self._pending.pop(reply.session_id, None)

        if not raw_msg or not raw_msg.from_user_id or not raw_msg.context_token:
            logger.warning("[WeChat] 找不到对应的 context_token，无法回复 session=%s", reply.session_id)
            return

        # 发送打字中状态（可选）
        if self.show_typing:
            await self._try_send_typing(raw_msg, TypingStatus.TYPING)

        await self._bot.send_text(
            to=raw_msg.from_user_id,
            text=reply.content,
        )

        # 取消打字中状态
        if self.show_typing:
            await self._try_send_typing(raw_msg, TypingStatus.CANCEL)

        logger.info("[WeChat] 已回复 user=%s", reply.user_id)

    async def _try_send_typing(self, raw_msg, status: TypingStatus) -> None:
        try:
            config = await self._bot.get_config(raw_msg.from_user_id)
            if config.typing_ticket:
                await self._bot.send_typing(
                    to=raw_msg.from_user_id,
                    typing_ticket=config.typing_ticket,
                    status=status,
                )
        except Exception as e:
            logger.debug("[WeChat] send_typing 失败（忽略）: %s", e)
            
    async def get_history(self, session_id: str) -> list[dict]:
        # 接入 Redis / 数据库时在此扩展
        return []

    # ─────────────────────────────────────────────
    # 登录 & 生命周期（由 Gateway 外部调用）
    # ─────────────────────────────────────────────

    async def login(self) -> bool:
        """尝试加载已保存账号，失败则扫码登录"""
        if await self._bot.load_saved_account():
            logger.info("[WeChat] 已加载保存的账号")
            return True
        logger.info("[WeChat] 开始扫码登录...")
        success = await self._bot.login(verbose=True)
        if not success:
            logger.error("[WeChat] 登录失败")
        return success

    async def start(self) -> None:
        """启动 SDK 消息监听（内部无限循环）"""
        await self._bot.start()

    async def stop(self) -> None:
        await self._bot.stop()