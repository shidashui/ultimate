"""
Authentication and login flow
"""

import asyncio
import json
import logging
from typing import Optional, Callable, Any
from datetime import datetime

import aiohttp

from .types import (
    QRCodeResponse,
    StatusResponse,
    LoginStartResult,
    LoginWaitResult,
)
from .exceptions import LoginError, NetworkError

logger = logging.getLogger(__name__)


class WeixinAuth:
    """Weixin authentication handler"""

    # Constants
    ACTIVE_LOGIN_TTL_MS = 5 * 60 * 1000  # 5 minutes
    QR_LONG_POLL_TIMEOUT_MS = 35_000  # 35 seconds
    DEFAULT_ILINK_BOT_TYPE = "3"
    MAX_QR_REFRESH_COUNT = 3

    def __init__(self, config):
        self.config = config
        self._active_logins: dict = {}

    async def start_login(
        self,
        base_url: str,
        bot_type: str = "3",
    ) -> LoginStartResult:
        """
        Start login flow and get QR code

        Args:
            base_url: API base URL
            bot_type: Bot type (default: "3")

        Returns:
            LoginStartResult with QR code URL
        """
        import uuid
        session_key = str(uuid.uuid4())

        url = f"{base_url.rstrip('/')}/ilink/bot/get_bot_qrcode?bot_type={bot_type}"
        logger.info(f"Fetching QR code from: {url}")

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        body = await resp.text()
                        raise LoginError(f"Failed to fetch QR code: {resp.status} {body}")

                    # API returns application/octet-stream but content is JSON
                    body = await resp.read()
                    data = json.loads(body)
                    qr_response = QRCodeResponse(
                        qrcode=data["qrcode"],
                        qrcode_img_content=data["qrcode_img_content"],
                    )

        except aiohttp.ClientError as e:
            raise NetworkError(f"Network error fetching QR code: {e}")

        logger.info(f"QR code received, qrcode={qr_response.qrcode[:20]}...")
        logger.info(f"QR Code URL: {qr_response.qrcode_img_content}")

        # Store active login
        self._active_logins[session_key] = {
            "qrcode": qr_response.qrcode,
            "qrcode_url": qr_response.qrcode_img_content,
            "started_at": datetime.now(),
        }

        return LoginStartResult(
            qrcode_url=qr_response.qrcode_img_content,
            message="使用微信扫描以下二维码，以完成连接。",
            session_key=session_key,
        )

    async def _poll_qr_status(
        self,
        base_url: str,
        qrcode: str,
    ) -> StatusResponse:
        """
        Poll QR code status (long poll)

        Args:
            base_url: API base URL
            qrcode: QR code identifier

        Returns:
            StatusResponse with current status
        """
        url = f"{base_url.rstrip('/')}/ilink/bot/get_qrcode_status?qrcode={qrcode}"
        logger.debug(f"Polling QR status from: {url}")

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers={"iLink-App-ClientVersion": "1"},
                    timeout=aiohttp.ClientTimeout(total=self.QR_LONG_POLL_TIMEOUT_MS / 1000),
                ) as resp:
                    if resp.status != 200:
                        body = await resp.text()
                        raise LoginError(f"Failed to poll QR status: {resp.status} {body}")

                    # API returns application/octet-stream but content is JSON
                    body = await resp.read()
                    data = json.loads(body)
                    return StatusResponse(
                        status=data.get("status", "wait"),
                        bot_token=data.get("bot_token"),
                        ilink_bot_id=data.get("ilink_bot_id"),
                        baseurl=data.get("baseurl"),
                        ilink_user_id=data.get("ilink_user_id"),
                    )

        except asyncio.TimeoutError:
            logger.debug("QR status poll timeout, returning wait")
            return StatusResponse(status="wait")

        except aiohttp.ClientError as e:
            logger.error(f"Network error polling QR status: {e}")
            raise NetworkError(f"Network error: {e}")

    async def wait_for_login(
        self,
        session_key: str,
        base_url: str,
        bot_type: str = "3",
        timeout_ms: int = 480_000,
        verbose: bool = False,
        status_callback: Optional[Callable[[str], Any]] = None,
    ) -> LoginWaitResult:
        """
        Wait for user to scan QR code and confirm login

        Args:
            session_key: Session key from start_login
            base_url: API base URL
            bot_type: Bot type
            timeout_ms: Total timeout in milliseconds
            verbose: Print verbose output
            status_callback: Optional callback for status updates

        Returns:
            LoginWaitResult with connection status
        """
        active_login = self._active_logins.get(session_key)
        if not active_login:
            return LoginWaitResult(
                connected=False,
                message="当前没有进行中的登录，请先发起登录。"
            )

        deadline = asyncio.get_event_loop().time() + (timeout_ms / 1000)
        scanned_printed = False
        qr_refresh_count = 1

        logger.info("Starting to poll QR code status...")

        while asyncio.get_event_loop().time() < deadline:
            try:
                status_response = await self._poll_qr_status(
                    base_url, active_login["qrcode"]
                )

                status = status_response.status
                logger.debug(f"QR status: {status}")

                if status == "wait":
                    if verbose:
                        print(".", end="", flush=True)

                elif status == "scaned":
                    if not scanned_printed:
                        msg = "\n👀 已扫码，在微信继续操作...\n"
                        print(msg)
                        if status_callback:
                            await status_callback(msg)
                        scanned_printed = True

                elif status == "expired":
                    qr_refresh_count += 1
                    if qr_refresh_count > self.MAX_QR_REFRESH_COUNT:
                        logger.warning(f"QR expired {self.MAX_QR_REFRESH_COUNT} times, giving up")
                        del self._active_logins[session_key]
                        return LoginWaitResult(
                            connected=False,
                            message="登录超时：二维码多次过期，请重新开始登录流程。"
                        )

                    msg = f"\n⏳ 二维码已过期，正在刷新...({qr_refresh_count}/{self.MAX_QR_REFRESH_COUNT})\n"
                    print(msg)
                    if status_callback:
                        await status_callback(msg)

                    # Refresh QR code
                    try:
                        new_result = await self.start_login(base_url, bot_type)
                        active_login["qrcode"] = self._active_logins[new_result.session_key]["qrcode"]
                        active_login["qrcode_url"] = new_result.qrcode_url
                        active_login["started_at"] = datetime.now()
                        scanned_printed = False
                        logger.info(f"New QR code obtained: {new_result.qrcode_url}")
                        print(f"🔄 新二维码已生成，请重新扫描\n")
                    except Exception as e:
                        logger.error(f"Failed to refresh QR code: {e}")
                        del self._active_logins[session_key]
                        return LoginWaitResult(
                            connected=False,
                            message=f"刷新二维码失败: {e}"
                        )

                elif status == "confirmed":
                    if not status_response.ilink_bot_id:
                        del self._active_logins[session_key]
                        return LoginWaitResult(
                            connected=False,
                            message="登录失败：服务器未返回 ilink_bot_id。"
                        )

                    del self._active_logins[session_key]
                    logger.info(f"Login confirmed! account={status_response.ilink_bot_id}")

                    return LoginWaitResult(
                        connected=True,
                        bot_token=status_response.bot_token,
                        account_id=status_response.ilink_bot_id,
                        base_url=status_response.baseurl,
                        user_id=status_response.ilink_user_id,
                        message="✅ 与微信连接成功！"
                    )

            except Exception as e:
                logger.error(f"Error polling QR status: {e}")
                del self._active_logins[session_key]
                return LoginWaitResult(
                    connected=False,
                    message=f"Login failed: {e}"
                )

            await asyncio.sleep(1)

        # Timeout
        logger.warning(f"Login timed out after {timeout_ms}ms")
        del self._active_logins[session_key]
        return LoginWaitResult(
            connected=False,
            message="登录超时，请重试。"
        )
