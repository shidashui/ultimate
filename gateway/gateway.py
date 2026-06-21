# gateway.py
import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from agentd.context.session import SessionStore
from config.configs import WORKSPACE_DIR
from agentd.agent.runner import AgentRunner

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# 数据结构
# ─────────────────────────────────────────────

@dataclass
class Message:
    platform: str
    user_id: str
    session_id: str
    content: str
    raw: dict = field(default_factory=dict)


@dataclass
class Reply:
    content: str
    platform: str
    user_id: str
    session_id: str


# ─────────────────────────────────────────────
# 抽象基类
# ─────────────────────────────────────────────

class BasePlatform(ABC):
    platform_name: str = ""
    channel: str = "unknown"       # 子类覆盖这一行即可

    @abstractmethod
    async def receive(self) -> Message: ...

    @abstractmethod
    async def send(self, reply: Reply) -> None: ...

    async def login(self) -> bool:
        return True

    async def start(self) -> None: ...

    async def stop(self) -> None: ...


# ─────────────────────────────────────────────
# Gateway
# ─────────────────────────────────────────────

class Gateway:

    def __init__(self):
        self._platforms: dict[str, BasePlatform] = {}
        self._tasks: list[asyncio.Task] = []

        # per-user 状态，key = user_id
        self._user_stores: dict[str, SessionStore] = {}
        self._user_messages: dict[str, list[dict]] = {}

        # 用户锁，防止同一用户的消息并发处理导致状态混乱
        self._user_locks: dict[str, asyncio.Lock] = {}

        self.runner = AgentRunner()

    # ── 注册平台 ──────────────────────────────────
    def register(self, platform: BasePlatform) -> "Gateway":
        if not platform.platform_name:
            raise ValueError(f"{type(platform).__name__} 必须设置 platform_name")
        self._platforms[platform.platform_name] = platform
        logger.info("[Gateway] 注册平台: %s", platform.platform_name)
        return self

    # ── per-user SessionStore（懒加载）─────────────
    def _get_user_store(self, user_id: str, platform_name: str) -> SessionStore:
        if user_id not in self._user_stores:
            store = SessionStore(base_dir=WORKSPACE_DIR, agent_id=platform_name)
            store.set_user_name(user_id)
            sessions = store.list_sessions()
            if sessions:
                sid = sessions[0][0]
                self._user_messages[user_id] = store.load_session(sid)
                logger.info("[Gateway] 恢复会话 user=%s sid=%s", user_id, sid)
            else:
                store.create_session(platform_name)
                self._user_messages[user_id] = []
                logger.info("[Gateway] 新建会话 user=%s", user_id)
            self._user_stores[user_id] = store
        return self._user_stores[user_id]

    # ── 用户锁 ─────────────────────────────────────
    def _get_user_lock(self, user_id: str) -> asyncio.Lock:
        if user_id not in self._user_locks:
            self._user_locks[user_id] = asyncio.Lock()
        return self._user_locks[user_id]
    
    # ── 单条消息完整处理链（对标 Cli.handle_user_input）
    async def _handle_message(self, platform: BasePlatform, msg: Message) -> None:
        store    = self._get_user_store(msg.user_id, platform.platform_name)
        messages = self._user_messages[msg.user_id]

        async with self._get_user_lock(msg.user_id):
            reply = await self.runner.run_turn(
                user_input=msg.content,
                messages=messages,
                store=store,
                channel=platform.channel,
            )

        await platform.send(Reply(
            content=reply or "抱歉，处理消息时出现了问题，请稍后重试。",
            platform=msg.platform,
            user_id=msg.user_id,
            session_id=msg.session_id,
        ))

    # ── 单平台调度循环 ────────────────────────────
    async def _dispatch(self, platform: BasePlatform) -> None:
        while True:
            try:
                msg = await platform.receive()
                logger.info("[Gateway] %s 收到消息 user=%s", platform.platform_name, msg.user_id)
                asyncio.create_task(self._handle_message(platform, msg))
            except asyncio.CancelledError:
                logger.info("[Gateway] %s dispatch 已停止", platform.platform_name)
                break
            except Exception as e:
                logger.exception("[Gateway] %s 处理异常: %s", platform.platform_name, e)

    # ── 登录所有平台 ──────────────────────────────
    async def _login_all(self) -> list[BasePlatform]:
        async def login_one(p: BasePlatform) -> BasePlatform | None:
            try:
                if await p.login():
                    logger.info("[Gateway] %s 登录成功", p.platform_name)
                    return p
                logger.error("[Gateway] %s 登录失败，跳过", p.platform_name)
            except Exception as e:
                logger.exception("[Gateway] %s 登录异常: %s", p.platform_name, e)
            return None

        results = await asyncio.gather(*[login_one(p) for p in self._platforms.values()])
        return [p for p in results if p is not None]

    # ── 启动 ─────────────────────────────────────
    async def run(self) -> None:
        if not self._platforms:
            raise RuntimeError("没有注册任何平台")

        active = await self._login_all()
        if not active:
            raise RuntimeError("所有平台登录均失败")

        for p in active:
            self._tasks.append(asyncio.create_task(p.start(),         name=f"{p.platform_name}.start"))
            self._tasks.append(asyncio.create_task(self._dispatch(p), name=f"{p.platform_name}.dispatch"))

        logger.info("[Gateway] 运行中，平台: %s", [p.platform_name for p in active])
        try:
            await asyncio.gather(*self._tasks)
        except asyncio.CancelledError:
            pass

    # ── 停止 ─────────────────────────────────────
    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        await asyncio.gather(
            *[p.stop() for p in self._platforms.values()],
            return_exceptions=True,
        )
        logger.info("[Gateway] 已停止")