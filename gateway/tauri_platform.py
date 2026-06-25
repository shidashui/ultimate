# gateway/tauri_platform.py
import asyncio
import logging
from aiohttp import web

from gateway.gateway import BasePlatform, Message, Reply
from gateway.events import EVENT_HELLO

logger = logging.getLogger(__name__)

DEFAULT_WS_PORT = 18765


class TauriPlatform(BasePlatform):
    """Tauri 桌面应用平台 — WebSocket Server + 事件广播通道。"""

    platform_name = "tauri"
    channel = "desktop"

    def __init__(self, port: int = DEFAULT_WS_PORT):
        self.port = port
        self.connections: set[web.WebSocketResponse] = set()
        self._app: web.Application | None = None
        self._runner: web.AppRunner | None = None

    # ── WebSocket handler ──

    async def _ws_handler(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self.connections.add(ws)
        logger.info("[TauriPlatform] Client connected (%d total)", len(self.connections))

        try:
            async for msg in ws:
                if msg.type == web.WSMsgType.TEXT:
                    data = msg.json()
                    event = data.get("event", "")
                    if event == "hello":
                        logger.info("[TauriPlatform] Handshake: version=%s", data.get("version", "?"))
                    elif event == "close":
                        logger.info("[TauriPlatform] Client requested close")
        except Exception:
            logger.debug("[TauriPlatform] Client connection error", exc_info=True)
        finally:
            self.connections.discard(ws)
            logger.info("[TauriPlatform] Client disconnected (%d remaining)", len(self.connections))

        return ws

    # ── BasePlatform interface ──

    async def receive(self) -> Message:
        """Tauri 端没有主动推送消息给 Gateway 的语义，但接口要求实现。"""
        while True:
            await asyncio.sleep(3600)

    async def send(self, reply: Reply) -> None:
        """向所有 Tauri 客户端广播回复文本。"""
        await self.broadcast({"event": "text_chunk", "text": reply.content})

    # ── Broadcast API ──

    async def broadcast(self, event: dict) -> None:
        """向所有连接的 Tauri 客户端推送事件。自动清理死连接。"""
        dead: set[web.WebSocketResponse] = set()
        for ws in self.connections:
            try:
                await ws.send_json(event)
            except ConnectionError:
                dead.add(ws)
        self.connections -= dead

    # ── Lifecycle ──

    async def start(self) -> None:
        self._app = web.Application()
        self._app.router.add_get("/ws", self._ws_handler)
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "127.0.0.1", self.port)
        await site.start()
        logger.info("[TauriPlatform] WS server listening on ws://127.0.0.1:%d/ws", self.port)

    async def stop(self) -> None:
        for ws in list(self.connections):
            await ws.close()
        self.connections.clear()
        if self._runner:
            await self._runner.cleanup()
        logger.info("[TauriPlatform] WS server stopped")
