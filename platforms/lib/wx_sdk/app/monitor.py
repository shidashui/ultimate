"""
Message monitor (long-poll loop)
"""

import asyncio
import logging
from typing import Optional, Callable, Any

from .api import WeixinAPI
from .types import WeixinMessage, GetUpdatesResp
from .exceptions import SessionExpiredError, APIError
from .storage import AccountStorage

logger = logging.getLogger(__name__)


class MessageMonitor:
    """Message monitor with long-poll loop"""

    def __init__(
        self,
        api: WeixinAPI,
        config,
        storage: AccountStorage,
        account_id: str,
    ):
        self.api = api
        self.config = config
        self.storage = storage
        self.account_id = account_id
        self.consecutive_failures = 0
        self.is_paused = False
        self.pause_until = 0

    async def run(
        self,
        message_callback: Callable[[WeixinMessage], Any],
        error_callback: Optional[Callable[[Exception], Any]] = None,
        status_callback: Optional[Callable[[str], Any]] = None,
        stop_event: Optional[asyncio.Event] = None,
        initial_sync_buf: str = "",
    ):
        """
        Run message monitoring loop

        Args:
            message_callback: Callback for received messages
            error_callback: Optional callback for errors
            status_callback: Optional callback for status updates
            stop_event: Event to stop monitoring
            initial_sync_buf: Initial sync buffer
        """
        get_updates_buf = initial_sync_buf
        next_timeout_ms = self.config.long_poll_timeout_ms

        logger.info(f"Monitor started for account {self.account_id}")

        if status_callback:
            await status_callback("Monitor started")

        while not stop_event or not stop_event.is_set():
            # Check if paused
            if self.is_paused:
                if asyncio.get_event_loop().time() < self.pause_until:
                    remaining = int(self.pause_until - asyncio.get_event_loop().time())
                    logger.info(f"Session paused, {remaining}s remaining")
                    await asyncio.sleep(min(remaining, 60))
                    continue
                else:
                    self.is_paused = False
                    logger.info("Session pause ended")

            try:
                logger.debug(f"Polling with timeout {next_timeout_ms}ms")

                resp = await self.api.get_updates(
                    get_updates_buf=get_updates_buf,
                    timeout_ms=next_timeout_ms,
                )

                # Update timeout from server suggestion
                if resp.longpolling_timeout_ms and resp.longpolling_timeout_ms > 0:
                    next_timeout_ms = resp.longpolling_timeout_ms
                    logger.debug(f"Updated poll timeout to {next_timeout_ms}ms")
                # Check API error
                if resp.ret != 0 or (resp.errcode and resp.errcode != 0):
                    await self._handle_api_error(resp, status_callback)
                    continue

                # Success - reset failures
                self.consecutive_failures = 0

                # Save sync buffer
                if resp.get_updates_buf:
                    get_updates_buf = resp.get_updates_buf
                    self.storage.save_sync_buf(self.account_id, get_updates_buf)

                # Process messages
                for msg in resp.msgs:
                    logger.info(f"Received message from {msg.from_user_id}")
                    try:
                        await message_callback(msg)
                    except Exception as e:
                        logger.error(f"Message callback error: {e}")
                        if error_callback:
                            try:
                                await error_callback(e)
                            except:
                                pass

            except SessionExpiredError:
                logger.error("Session expired, pausing for 1 hour")
                self._pause_session()
                if status_callback:
                    await status_callback("Session expired, pausing for 1 hour")

            except asyncio.CancelledError:
                logger.info("Monitor cancelled")
                raise

            except Exception as e:
                logger.error(f"Monitor error: {e}")
                self.consecutive_failures += 1

                if status_callback:
                    await status_callback(f"Error: {e}")

                if error_callback:
                    try:
                        await error_callback(e)
                    except:
                        pass

                # Backoff strategy
                if self.consecutive_failures >= self.config.max_consecutive_failures:
                    delay = self.config.backoff_delay_ms / 1000
                    logger.warning(f"{self.consecutive_failures} failures, backing off {delay}s")
                    if status_callback:
                        await status_callback(f"Backing off {delay}s after errors")
                    await self._sleep_or_stop(delay, stop_event)
                    self.consecutive_failures = 0
                else:
                    delay = self.config.retry_delay_ms / 1000
                    await self._sleep_or_stop(delay, stop_event)

        logger.info("Monitor stopped")

    async def _handle_api_error(
        self,
        resp: GetUpdatesResp,
        status_callback: Optional[Callable[[str], Any]] = None,
    ):
        """Handle API error response"""
        errcode = resp.errcode or resp.ret
        errmsg = resp.errmsg or "Unknown error"

        logger.error(f"API error: ret={resp.ret} errcode={errcode} errmsg={errmsg}")

        if errcode == self.api.SESSION_EXPIRED_ERRCODE:
            raise SessionExpiredError()

        self.consecutive_failures += 1

    def _pause_session(self):
        """Pause session for configured duration"""
        self.is_paused = True
        self.pause_until = (
            asyncio.get_event_loop().time()
            + self.config.session_pause_duration_ms / 1000
        )

    async def _sleep_or_stop(
        self,
        seconds: float,
        stop_event: Optional[asyncio.Event] = None,
    ):
        """Sleep unless stop event is set"""
        if stop_event:
            try:
                await asyncio.wait_for(
                    stop_event.wait(),
                    timeout=seconds,
                )
            except asyncio.TimeoutError:
                pass
        else:
            await asyncio.sleep(seconds)
