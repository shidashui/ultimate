import asyncio
import logging
import hashlib
import mimetypes
import base64
from typing import Optional, Callable, List, Dict, Any
from dataclasses import dataclass, asdict
from pathlib import Path
from urllib.parse import quote
from pprint import pprint

from .auth import WeixinAuth
from .api import WeixinAPI
from .monitor import MessageMonitor
from .types import WeixinMessage, GetUpdatesResp, MessageItemType, MessageItem, TypingStatus, GetConfigResp
from .exceptions import WeixinBotError, LoginError
from .storage import AccountStorage
from .silk_transcode import silk_to_wav

logger = logging.getLogger(__name__)


@dataclass
class BotConfig:
    """Bot configuration"""
    base_url: str = "https://ilinkai.weixin.qq.com"
    cdn_base_url: str = "https://novac2c.cdn.weixin.qq.com/c2c"
    bot_type: str = "3"
    long_poll_timeout_ms: int = 35000
    max_consecutive_failures: int = 3
    backoff_delay_ms: int = 30000
    retry_delay_ms: int = 2000
    session_pause_duration_ms: int = 60 * 60 * 1000  # 1 hour


@dataclass
class MediaInfo:
    """Media information extracted from message"""
    type: int  # MessageItemType
    file_name: Optional[str] = None
    file_path: Optional[str] = None
    file_size: Optional[int] = None
    media_item: Optional[MessageItem] = None


class WeixinBot:
    """
    Weixin Bot main class

    Example:
        bot = WeixinBot()

        # Set up message callback
        @bot.on_message
        async def handle_message(message: WeixinMessage):
            print(f"Received: {message}")

        # Login with QR code
        await bot.login()

        # Start monitoring (blocking)
        await bot.start()
    """

    def __init__(
        self,
        config: Optional[BotConfig] = None,
        storage_path: Optional[str] = None,
    ):
        self.config = config or BotConfig()
        self.storage = AccountStorage(storage_path)

        # Components
        self.auth = WeixinAuth(self.config)
        self.api: Optional[WeixinAPI] = None
        self.monitor: Optional[MessageMonitor] = None

        # State
        self._account_id: Optional[str] = None
        self._token: Optional[str] = None
        self._is_logged_in = False
        self._is_running = False
        self._stop_event = asyncio.Event()
        self.context_token: Optional[str] = None  # Latest context token from received messages

        # Callbacks
        self._message_callback: Optional[Callable[[WeixinMessage], Any]] = None
        self._error_callback: Optional[Callable[[Exception], Any]] = None
        self._status_callback: Optional[Callable[[str], Any]] = None

    @property
    def is_logged_in(self) -> bool:
        """Check if bot is logged in"""
        return self._is_logged_in and self._token is not None

    @property
    def account_id(self) -> Optional[str]:
        """Get current account ID"""
        return self._account_id

    def on_message(self, callback: Callable[[WeixinMessage], Any]) -> Callable:
        """
        Set message received callback

        Args:
            callback: Async or sync function that receives WeixinMessage

        Returns:
            The callback function (for use as decorator)
        """
        self._message_callback = callback
        return callback

    def on_error(self, callback: Callable[[Exception], Any]) -> Callable:
        """
        Set error callback

        Args:
            callback: Async or sync function that receives Exception
        """
        self._error_callback = callback
        return callback

    def on_status(self, callback: Callable[[str], Any]) -> Callable:
        """
        Set status update callback

        Args:
            callback: Async or sync function that receives status string
        """
        self._status_callback = callback
        return callback

    async def _notify_status(self, message: str):
        """Notify status update"""
        logger.info(message)
        if self._status_callback:
            try:
                if asyncio.iscoroutinefunction(self._status_callback):
                    await self._status_callback(message)
                else:
                    self._status_callback(message)
            except Exception as e:
                logger.error(f"Status callback error: {e}")

    async def _notify_message(self, message: WeixinMessage):
        """Notify message received"""
        # Update context_token from received message
        if message.context_token:
            self.context_token = message.context_token
        
        if self._message_callback:
            try:
                if asyncio.iscoroutinefunction(self._message_callback):
                    await self._message_callback(message)
                else:
                    self._message_callback(message)
            except Exception as e:
                logger.error(f"Message callback error: {e}")
                if self._error_callback:
                    try:
                        if asyncio.iscoroutinefunction(self._error_callback):
                            await self._error_callback(e)
                        else:
                            self._error_callback(e)
                    except:
                        pass

    async def login(
        self,
        timeout_ms: int = 480000,
        verbose: bool = False,
    ) -> bool:
        """
        Login with QR code

        Args:
            timeout_ms: Login timeout in milliseconds (default: 8 minutes)
            verbose: Print verbose output

        Returns:
            True if login successful

        Raises:
            LoginError: If login fails
        """
        await self._notify_status("Starting Weixin login with QR code...")

        try:
            # Step 1: Start login and get QR code
            start_result = await self.auth.start_login(
                base_url=self.config.base_url,
                bot_type=self.config.bot_type,
            )

            if not start_result.qrcode_url:
                raise LoginError(f"Failed to get QR code: {start_result.message}")

            await self._notify_status(f"QR Code URL: {start_result.qrcode_url}")

            # Print QR code to console if qrcode-terminal is available
            try:
                import qrcode
                print("\n" + "="*50)
                print("Scan this QR code with Weixin:")
                print("="*50)
                qr = qrcode.QRCode(version=1, box_size=2, border=1)
                qr.add_data(start_result.qrcode_url)
                qr.make(fit=True)
                qr.print_ascii(invert=True)
                print("="*50 + "\n")
            except ImportError:
                print(f"\nPlease scan this QR code URL: {start_result.qrcode_url}\n")

            # Step 2: Wait for scan and confirmation
            await self._notify_status("Waiting for QR code scan...")

            wait_result = await self.auth.wait_for_login(
                session_key=start_result.session_key,
                base_url=self.config.base_url,
                bot_type=self.config.bot_type,
                timeout_ms=timeout_ms,
                verbose=verbose,
                status_callback=self._notify_status,
            )

            if not wait_result.connected:
                raise LoginError(f"Login failed: {wait_result.message}")

            # Step 3: Save credentials
            self._token = wait_result.bot_token
            self._account_id = wait_result.account_id

            # Save to storage
            self.storage.save_account(
                account_id=self._account_id,
                token=self._token,
                base_url=wait_result.base_url or self.config.base_url,
                user_id=wait_result.user_id,
            )

            # Initialize API client
            self.api = WeixinAPI(
                base_url=self.config.base_url,
                token=self._token,
                config=self.config,
            )

            self._is_logged_in = True
            await self._notify_status(f"Login successful! Account: {self._account_id}")

            return True

        except Exception as e:
            await self._notify_status(f"Login failed: {e}")
            raise LoginError(f"Login failed: {e}")

    async def login_with_token(
        self,
        account_id: str,
        token: str,
        base_url: Optional[str] = None,
    ) -> bool:
        """
        Login with existing token

        Args:
            account_id: Account ID
            token: Bot token
            base_url: Optional base URL (uses config default if not provided)

        Returns:
            True if login successful
        """
        self._account_id = account_id
        self._token = token
        self.api = WeixinAPI(
            base_url=base_url or self.config.base_url,
            token=token,
            config=self.config,
        )
        self._is_logged_in = True
        await self._notify_status(f"Logged in with token. Account: {account_id}")
        return True

    async def load_saved_account(self, account_id: Optional[str] = None) -> bool:
        """
        Load saved account from storage

        Args:
            account_id: Optional account ID (loads first available if not specified)

        Returns:
            True if account loaded successfully
        """
        accounts = self.storage.list_accounts()
        if not accounts:
            return False

        target_account = account_id or accounts[0]
        account_data = self.storage.load_account(target_account)

        if not account_data or not account_data.get("token"):
            return False

        return await self.login_with_token(
            account_id=target_account,
            token=account_data["token"],
            base_url=account_data.get("base_url"),
        )

    async def send_text(
        self,
        to: str,
        text: str,
    ) -> str:
        """
        Send text message

        Args:
            to: Recipient user ID
            text: Message text
            context_token: Optional conversation context token

        Returns:
            Message ID

        Raises:
            WeixinBotError: If not logged in or send fails
        """
        if not self.api:
            raise WeixinBotError("Not logged in")

        return await self.api.send_text(to, text, self.context_token)

    async def send_image(
        self,
        to: str,
        file_path: str,
        text: str = "",
    ) -> str:
        """
        Send image message

        Args:
            to: Recipient user ID
            file_path: Path to image file
            text: Optional caption text
            context_token: Optional conversation context token

        Returns:
            Message ID
        """
        if not self.api:
            raise WeixinBotError("Not logged in")

        return await self.api.send_image(to, file_path, text, self.context_token)

    async def send_file(
        self,
        to: str,
        file_path: str,
        text: str = "",
    ) -> str:
        """
        Send file attachment

        Args:
            to: Recipient user ID
            file_path: Path to file
            text: Optional caption text
            context_token: Optional conversation context token

        Returns:
            Message ID
        """
        if not self.api:
            raise WeixinBotError("Not logged in")            
        return await self.api.send_file(to, file_path, text, self.context_token)
    
    async def send_video(
        self,
        to: str,
        file_path: str,
        text: str = "",
    ) -> str:
        """
        Send file attachment

        Args:
            to: Recipient user ID
            file_path: Path to file
            text: Optional caption text
            context_token: Optional conversation context token

        Returns:
            Message ID
        """
        if not self.api:
            raise WeixinBotError("Not logged in")

        return await self.api.send_video(to, file_path, text, self.context_token)

    async def send_typing(
        self,
        to: str,
        typing_ticket: str,
        status: TypingStatus = TypingStatus.TYPING,
    ) -> None:
        """
        Send typing indicator to a user

        Args:
            to: Recipient user ID
            typing_ticket: Typing ticket from get_config
            status: TypingStatus.TYPING (1) or TypingStatus.CANCEL (2)

        Raises:
            WeixinBotError: If not logged in or send fails
        """
        if not self.api:
            raise WeixinBotError("Not logged in")

        await self.api.send_typing(to, typing_ticket, status)

    async def get_config(self, ilink_user_id: str) -> GetConfigResp:
        """
        Fetch bot config (includes typing_ticket) for a given user

        Args:
            ilink_user_id: User ID to get config for

        Returns:
            GetConfigResp with typing_ticket

        Raises:
            WeixinBotError: If not logged in
        """
        if not self.api:
            raise WeixinBotError("Not logged in")

        return await self.api.get_config(ilink_user_id, self.context_token)

    async def start(self):
        """
        Start message monitoring (blocking)

        This method starts the long-poll loop and blocks until stop() is called.
        """
        if not self.is_logged_in:
            raise WeixinBotError("Not logged in. Call login() first.")

        if self._is_running:
            raise WeixinBotError("Already running")

        self._is_running = True
        self._stop_event.clear()

        await self._notify_status("Starting message monitor...")

        # Initialize monitor
        self.monitor = MessageMonitor(
            api=self.api,
            config=self.config,
            storage=self.storage,
            account_id=self._account_id,
        )

        # Load sync buffer if exists
        sync_buf = self.storage.load_sync_buf(self._account_id)

        try:
            await self.monitor.run(
                message_callback=self._notify_message,
                error_callback=self._error_callback,
                status_callback=self._notify_status,
                stop_event=self._stop_event,
                initial_sync_buf=sync_buf,
            )
        finally:
            self._is_running = False
            await self._notify_status("Monitor stopped")

    async def stop(self):
        """Stop message monitoring"""
        await self._notify_status("Stopping...")
        self._stop_event.set()

    async def process_message(
        self,
        message: WeixinMessage,
        save_dir: Optional[str] = None,
    ) -> tuple[str, Optional[MediaInfo]]:
        """
        Process a message and extract content

        Args:
            message: Weixin message
            save_dir: Optional directory to save media files

        Returns:
            Tuple of (text_content, media_info or None)
        """
        text_content = ""
        media_info: Optional[MediaInfo] = None

        # Extract text from item_list
        for item in message.item_list:
            if item.type == MessageItemType.TEXT and item.text_item:
                text_content = item.text_item.text or ""
                break

        # Find media item (priority: IMAGE > VIDEO > FILE > VOICE)
        media_item = (
            self._find_media_item(message, MessageItemType.IMAGE) or
            self._find_media_item(message, MessageItemType.VIDEO) or
            self._find_media_item(message, MessageItemType.FILE) or
            self._find_media_item(message, MessageItemType.VOICE)
        )

        if media_item and save_dir:
            media_info = await self._save_media_item(media_item, save_dir)

        return text_content, media_info

    def _find_media_item(
        self,
        message: WeixinMessage,
        item_type: int
    ) -> Optional[MessageItem]:
        """Find media item of specific type in message"""
        for item in message.item_list:
            if item.type != item_type:
                continue

            if item_type == MessageItemType.IMAGE and item.image_item and item.image_item.media:
                return item
            elif item_type == MessageItemType.VIDEO and item.video_item and item.video_item.media:
                return item
            elif item_type == MessageItemType.FILE and item.file_item and item.file_item.media:
                return item
            elif item_type == MessageItemType.VOICE and item.voice_item and item.voice_item.media:
                return item

        return None

    async def _save_media_item(
        self,
        item: MessageItem,
        save_dir: str
    ) -> Optional[MediaInfo]:
        """
        Save media item to local directory.
        Different media types have different download handling.

        Args:
            item: Media message item
            save_dir: Directory to save the file

        Returns:
            MediaInfo with saved file info
        """
        result: Optional[MediaInfo] = None
        save_path = Path(save_dir)
        save_path.mkdir(parents=True, exist_ok=True)
        
        pprint(asdict(item), indent=2)
        
        if item.type == MessageItemType.IMAGE:
            result = await self._download_and_save_image(item, save_path)
        elif item.type == MessageItemType.VOICE:
            result = await self._download_and_save_voice(item, save_path)
        elif item.type == MessageItemType.FILE:
            result = await self._download_and_save_file(item, save_path)
        elif item.type == MessageItemType.VIDEO:
            result = await self._download_and_save_video(item, save_path)

        return result

    async def _download_media(
        self,
        encrypt_query_param: str,
        aes_key_base64: Optional[str],
        label: str
    ) -> Optional[bytes]:
        """
        Download and decrypt media from CDN.

        Args:
            encrypt_query_param: CDN encrypt query param
            aes_key_base64: Base64 encoded AES key (None for plaintext download)
            label: Label for logging

        Returns:
            Decrypted media bytes or None on failure
        """
        import aiohttp
        from .utils import aes_ecb_decrypt, parse_aes_key

        cdn_url = f"{self.config.cdn_base_url}/download?encrypted_query_param={quote(encrypt_query_param, safe='')}"
        logger.debug(f'{label}: cdn_url={cdn_url}')

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(cdn_url) as resp:
                    if resp.status != 200:
                        logger.error(f"Failed to download media: {resp.status}")
                        return None
                    encrypted_data = await resp.read()

            # Decrypt if AES key is available
            if aes_key_base64:
                try:
                    aes_key = parse_aes_key(aes_key_base64)
                    decrypted_data = aes_ecb_decrypt(encrypted_data, aes_key)
                    return decrypted_data
                except Exception as e:
                    logger.warning(f"Failed to decrypt media, using encrypted: {e}")
                    return encrypted_data
            else:
                # Plaintext download (no encryption)
                return encrypted_data

        except Exception as e:
            logger.error(f"Error downloading media: {e}")
            return None

    async def _download_and_save_image(
        self,
        item: MessageItem,
        save_path: Path
    ) -> Optional[MediaInfo]:
        """Download and save image media."""
        if not item.image_item or not item.image_item.media:
            return None

        img = item.image_item
        media = img.media

        if not media.encrypt_query_param:
            return None

        # Priority: image_item.aeskey (hex) -> media.aes_key (base64)
        aes_key_base64: Optional[str] = None
        aeskey_source = "none"
        if img.aeskey:
            try:
                aes_key_base64 = base64.b64encode(bytes.fromhex(img.aeskey)).decode('ascii')
                aeskey_source = "image_item.aeskey"
            except ValueError:
                pass
        if not aes_key_base64 and media.aes_key:
            aes_key_base64 = media.aes_key
            aeskey_source = "media.aes_key"

        logger.debug(
            f"Image: encrypt_query_param={media.encrypt_query_param[:40]}... "
            f"hasAesKey={bool(aes_key_base64)} aeskeySource={aeskey_source}"
        )

        data = await self._download_media(
            media.encrypt_query_param,
            aes_key_base64,
            "image"
        )

        if data is None:
            return None

        # Generate filename and save
        file_hash = hashlib.md5(data).hexdigest()[:8]
        final_file_name = f"image_{file_hash}.jpg"
        file_path = save_path / final_file_name
        file_path.write_bytes(data)

        logger.info(f"Saved IMAGE to {file_path}")

        return MediaInfo(
            type=item.type,
            file_name=final_file_name,
            file_path=str(file_path),
            file_size=len(data),
            media_item=item,
        )

    async def _download_and_save_voice(
        self,
        item: MessageItem,
        save_path: Path
    ) -> Optional[MediaInfo]:
        """Download and save voice media (with SILK to WAV transcoding)."""
        if not item.voice_item or not item.voice_item.media:
            return None

        voice = item.voice_item
        media = voice.media

        if not media.encrypt_query_param or not media.aes_key:
            return None

        logger.debug(f"Voice: downloading with aes_key")

        silk_data = await self._download_media(
            media.encrypt_query_param,
            media.aes_key,
            "voice"
        )

        if silk_data is None:
            return None

        logger.debug(f"Voice: decrypted {len(silk_data)} bytes, attempting silk transcode")

        # Try to transcode SILK to WAV
        wav_data = silk_to_wav(silk_data)

        if wav_data:
            file_hash = hashlib.md5(wav_data).hexdigest()[:8]
            final_file_name = f"voice_{file_hash}.wav"
            file_path = save_path / final_file_name
            file_path.write_bytes(wav_data)

            logger.info(f"Saved VOICE (WAV) to {file_path}")

            return MediaInfo(
                type=item.type,
                file_name=final_file_name,
                file_path=str(file_path),
                file_size=len(wav_data),
                media_item=item,
            )
        else:
            # Fallback: save raw SILK
            file_hash = hashlib.md5(silk_data).hexdigest()[:8]
            final_file_name = f"voice_{file_hash}.silk"
            file_path = save_path / final_file_name
            file_path.write_bytes(silk_data)

            logger.info(f"Voice: silk transcode unavailable, saved raw SILK to {file_path}")

            return MediaInfo(
                type=item.type,
                file_name=final_file_name,
                file_path=str(file_path),
                file_size=len(silk_data),
                media_item=item,
            )

    async def _download_and_save_file(
        self,
        item: MessageItem,
        save_path: Path
    ) -> Optional[MediaInfo]:
        """Download and save file media."""
        if not item.file_item or not item.file_item.media:
            return None

        file_item = item.file_item
        media = file_item.media

        if not media.encrypt_query_param or not media.aes_key:
            return None

        data = await self._download_media(
            media.encrypt_query_param,
            media.aes_key,
            "file"
        )

        if data is None:
            return None

        # Detect MIME type from filename
        file_name = file_item.file_name or "file.bin"
        mime_type, _ = mimetypes.guess_type(file_name)
        if mime_type is None:
            mime_type = "application/octet-stream"

        # Generate filename
        file_hash = hashlib.md5(data).hexdigest()[:8]
        final_file_name = f"{file_hash}_{file_name}"
        file_path = save_path / final_file_name
        file_path.write_bytes(data)

        logger.info(f"Saved FILE to {file_path} mime={mime_type}")

        return MediaInfo(
            type=item.type,
            file_name=final_file_name,
            file_path=str(file_path),
            file_size=len(data),
            media_item=item,
        )

    async def _download_and_save_video(
        self,
        item: MessageItem,
        save_path: Path
    ) -> Optional[MediaInfo]:
        """Download and save video media."""
        if not item.video_item or not item.video_item.media:
            return None

        video = item.video_item
        media = video.media

        if not media.encrypt_query_param or not media.aes_key:
            return None

        data = await self._download_media(
            media.encrypt_query_param,
            media.aes_key,
            "video"
        )

        if data is None:
            return None

        # Generate filename (always as mp4)
        file_hash = hashlib.md5(data).hexdigest()[:8]
        final_file_name = f"video_{file_hash}.mp4"
        file_path = save_path / final_file_name
        file_path.write_bytes(data)

        logger.info(f"Saved VIDEO to {file_path}")

        return MediaInfo(
            type=item.type,
            file_name=final_file_name,
            file_path=str(file_path),
            file_size=len(data),
            media_item=item,
        )

    def run(self):
        """
        Run bot (blocking, sync interface)

        Example:
            bot = WeixinBot()
            # ... setup callbacks and login ...
            bot.run()
        """
        asyncio.run(self.start())
