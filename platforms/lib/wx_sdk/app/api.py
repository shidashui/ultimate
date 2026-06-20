"""
Weixin API client
"""

import logging
import hashlib
import secrets
import base64
from typing import Optional, Dict, Any
from pathlib import Path

import aiohttp

from .types import (
    GetUpdatesReq,
    GetUpdatesResp,
    GetUploadUrlReq,
    GetUploadUrlResp,
    SendMessageReq,
    SendTypingReq,
    SendTypingResp,
    GetConfigResp,
    WeixinMessage,
    MessageItem,
    MessageItemType,
    MessageType,
    MessageState,
    TextItem,
    BaseInfo,
    UploadedFileInfo,
    UploadMediaType,
    TypingStatus,
)
from .exceptions import APIError, NetworkError, SessionExpiredError
from .utils import markdown_to_plain_text, aes_ecb_padded_size, aes_ecb_encrypt

logger = logging.getLogger(__name__)


class WeixinAPI:
    """Weixin API client"""

    DEFAULT_API_TIMEOUT_MS = 15_000
    DEFAULT_CONFIG_TIMEOUT_MS = 10_000
    SESSION_EXPIRED_ERRCODE = -14

    def __init__(self, base_url: str, token: str, config):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.config = config
        self._channel_version = "0.1.0"
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    def _build_headers(self, body: str) -> Dict[str, str]:
        """Build request headers"""
        # X-WECHAT-UIN: random uint32 -> decimal string -> base64
        uint32 = secrets.randbits(32)
        wechat_uin = str(uint32).encode().hex()

        headers = {
            "Content-Type": "application/json",
            "AuthorizationType": "ilink_bot_token",
            "Content-Length": str(len(body.encode("utf-8"))),
            "X-WECHAT-UIN": wechat_uin,
        }

        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        return headers

    def _build_base_info(self) -> BaseInfo:
        """Build base info for requests"""
        return BaseInfo(channel_version=self._channel_version)

    async def _api_fetch(
        self,
        endpoint: str,
        body: str,
        timeout_ms: int,
        label: str,
    ) -> str:
        """
        Make API request

        Args:
            endpoint: API endpoint (e.g., "ilink/bot/getupdates")
            body: Request body JSON string
            timeout_ms: Timeout in milliseconds
            label: Label for logging

        Returns:
            Response body string

        Raises:
            APIError: If API returns error
            NetworkError: If network error occurs
        """
        url = f"{self.base_url}/{endpoint}"
        headers = self._build_headers(body)

        logger.debug(f"POST {url} body={body}")

        try:
            session = await self._get_session()
            async with session.post(
                url,
                headers=headers,
                data=body,
                timeout=aiohttp.ClientTimeout(total=timeout_ms / 1000),
            ) as resp:
                raw_text = await resp.text()
                logger.debug(f"{label} status={resp.status}")
                if resp.status != 200:
                    raise APIError(f"{label} {resp.status}: {raw_text}")

                return raw_text

        except aiohttp.ClientError as e:
            raise NetworkError(f"Network error: {e}")

    async def get_updates(
        self,
        get_updates_buf: str = "",
        timeout_ms: int = 35000,
    ) -> GetUpdatesResp:
        """
        Get updates (long poll)

        Args:
            get_updates_buf: Sync buffer from previous response
            timeout_ms: Long poll timeout

        Returns:
            GetUpdatesResp with messages
        """
        req = GetUpdatesReq(
            get_updates_buf=get_updates_buf,
            base_info=self._build_base_info(),
        )
        body = self._dataclass_to_json(req)
        try:
            raw = await self._api_fetch(
                "ilink/bot/getupdates",
                body,
                timeout_ms,
                "getUpdates",
            )
            data = self._json_to_get_updates_resp(raw)

            # Check for session expired
            if data.errcode == self.SESSION_EXPIRED_ERRCODE or data.ret == self.SESSION_EXPIRED_ERRCODE:
                raise SessionExpiredError("Session expired")

            return data

        except asyncio.TimeoutError:
            # Long poll timeout is normal
            logger.debug(f"getUpdates timeout after {timeout_ms}ms")
            return GetUpdatesResp(ret=0, msgs=[], get_updates_buf=get_updates_buf)

    async def send_message(self, message: WeixinMessage) -> None:
        """
        Send message

        Args:
            message: Message to send
        """
        req = SendMessageReq(msg=message)
        body = self._dataclass_to_json(req, include_base_info=True)

        await self._api_fetch(
            "ilink/bot/sendmessage",
            body,
            self.DEFAULT_API_TIMEOUT_MS,
            "sendMessage",
        )

    async def send_text(
        self,
        to: str,
        text: str,
        context_token: Optional[str] = None,
    ) -> str:
        """
        Send text message

        Args:
            to: Recipient user ID
            text: Message text
            context_token: Conversation context token

        Returns:
            Message ID
        """
        import uuid
        client_id = f"openclaw-weixin-{uuid.uuid4().hex[:16]}"

        plain_text = markdown_to_plain_text(text)

        message = WeixinMessage(
            to_user_id=to,
            from_user_id="",
            client_id=client_id,
            message_type=MessageType.BOT,
            message_state=MessageState.FINISH,
            item_list=[MessageItem(
                type=MessageItemType.TEXT,
                text_item=TextItem(text=plain_text),
            )],
            context_token=context_token,
        )

        await self.send_message(message)
        return client_id

    async def get_upload_url(self, req: GetUploadUrlReq) -> GetUploadUrlResp:
        """
        Get upload URL for file

        Args:
            req: Upload URL request

        Returns:
            GetUploadUrlResp with upload parameters
        """
        body = self._dataclass_to_json(req, include_base_info=True)

        raw = await self._api_fetch(
            "ilink/bot/getuploadurl",
            body,
            self.DEFAULT_API_TIMEOUT_MS,
            "getUploadUrl",
        )

        data = self._json_to_get_upload_url_resp(raw)
        return data

    async def upload_file_to_cdn(
        self,
        file_path: str,
        to_user_id: str,
        media_type: UploadMediaType,
    ) -> UploadedFileInfo:
        """
        Upload file to Weixin CDN

        Args:
            file_path: Path to file
            to_user_id: Recipient user ID
            media_type: Media type (IMAGE, VIDEO, FILE)

        Returns:
            UploadedFileInfo
        """
        from .cdn import CdnUploader

        uploader = CdnUploader(self)
        return await uploader.upload_file(file_path, to_user_id, media_type)

    async def send_image(
        self,
        to: str,
        file_path: str,
        text: str = "",
        context_token: Optional[str] = None,
    ) -> str:
        """Send image message"""
        # Upload file first
        uploaded = await self.upload_file_to_cdn(
            file_path, to, UploadMediaType.IMAGE
        )
        try:
            aes_key_base64 = base64.b64encode(uploaded.aeskey.encode('utf-8')).decode('utf-8')            
        except ValueError:
            pass
        # Build and send message
        import uuid
        client_id = f"openclaw-weixin-{uuid.uuid4().hex[:16]}"
        
        message = WeixinMessage(
            to_user_id=to,
            from_user_id="",
            client_id=client_id,
            message_type=MessageType.BOT,
            message_state=MessageState.FINISH,
            item_list=[MessageItem(
                type=MessageItemType.IMAGE,
                image_item={
                    "media": {
                        "encrypt_query_param": uploaded.download_encrypted_query_param,
                        "aes_key": aes_key_base64,  # base64 encoded
                        "encrypt_type": 1,
                    },
                    "mid_size": uploaded.file_size_ciphertext,
                },
            )],
            context_token=context_token,
        )
        if text is not None and len(text) > 0:
            message.item_list.append(MessageItem(type=MessageItemType.TEXT, text_item=TextItem(text=text)))
        await self.send_message(message)
        return client_id

    async def send_file(
        self,
        to: str,
        file_path: str,
        text: str = "",
        context_token: Optional[str] = None,
    ) -> str:
        """Send file attachment"""
        # Upload file first
        uploaded = await self.upload_file_to_cdn(
            file_path, to, UploadMediaType.FILE
        )

        import uuid
        from pathlib import Path
        client_id = f"openclaw-weixin-{uuid.uuid4().hex[:16]}"
        file_name = Path(file_path).name
        try:
            aes_key_base64 = base64.b64encode(uploaded.aeskey.encode('utf-8')).decode('utf-8')            
        except ValueError:
            pass
    
        message = WeixinMessage(
            to_user_id=to,
            from_user_id="",
            client_id=client_id,
            message_type=MessageType.BOT,
            message_state=MessageState.FINISH,
            item_list=[MessageItem(
                type=MessageItemType.FILE,
                file_item={
                    "media": {
                        "encrypt_query_param": uploaded.download_encrypted_query_param,
                        "aes_key": aes_key_base64,
                        "encrypt_type": 1,
                    },
                    "file_name": file_name,
                    "len": str(uploaded.file_size),
                },
            )],
            context_token=context_token,
        )
        if text is not None and len(text) > 0:
            message.item_list.append(MessageItem(type=MessageItemType.TEXT, text_item=TextItem(text=text)))
        await self.send_message(message)
        return client_id

    async def send_video(
        self,
        to: str,
        file_path: str,
        text: str = "",
        context_token: Optional[str] = None,
    ) -> str:
        """Send video message"""
        # Upload file first
        uploaded = await self.upload_file_to_cdn(
            file_path, to, UploadMediaType.VIDEO
        )

        import uuid
        from pathlib import Path
        client_id = f"openclaw-weixin-{uuid.uuid4().hex[:16]}"
        try:
            aes_key_base64 = base64.b64encode(uploaded.aeskey.encode('utf-8')).decode('utf-8')
        except ValueError:
            pass
        message = WeixinMessage(
            to_user_id=to,
            from_user_id="",
            client_id=client_id,
            message_type=MessageType.BOT,
            message_state=MessageState.FINISH,
            item_list=[MessageItem(
                type=MessageItemType.VIDEO,
                video_item={
                    "media": {
                        "encrypt_query_param": uploaded.download_encrypted_query_param,
                        "aes_key": aes_key_base64,
                        "encrypt_type": 1,
                    },
                    "video_size": uploaded.file_size,
                },
            )],
            context_token=context_token,
        )
        if text is not None and len(text) > 0:
            message.item_list.append(MessageItem(type=MessageItemType.TEXT, text_item=TextItem(text=text)))
        await self.send_message(message)
        return client_id

    async def get_config(
        self,
        ilink_user_id: str,
        context_token: Optional[str] = None,
    ) -> GetConfigResp:
        """
        Fetch bot config (includes typing_ticket) for a given user

        Args:
            ilink_user_id: User ID to get config for
            context_token: Optional conversation context token

        Returns:
            GetConfigResp with typing_ticket
        """
        import json
        body = json.dumps({
            "ilink_user_id": ilink_user_id,
            "context_token": context_token,
            "base_info": {"channel_version": self._channel_version},
        })

        raw = await self._api_fetch(
            "ilink/bot/getconfig",
            body,
            self.DEFAULT_CONFIG_TIMEOUT_MS,
            "getConfig",
        )

        data = json.loads(raw)
        return GetConfigResp(
            ret=data.get("ret", 0),
            errmsg=data.get("errmsg"),
            typing_ticket=data.get("typing_ticket"),
        )

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
        """
        req = SendTypingReq(
            ilink_user_id=to,
            typing_ticket=typing_ticket,
            status=status,
        )
        body = self._dataclass_to_json(req, include_base_info=True)

        await self._api_fetch(
            "ilink/bot/sendtyping",
            body,
            self.DEFAULT_CONFIG_TIMEOUT_MS,
            "sendTyping",
        )

    async def close(self):
        """Close API client"""
        if self._session and not self._session.closed:
            await self._session.close()

    def _dataclass_to_json(self, obj: Any, include_base_info: bool = False) -> str:
        """Convert dataclass to JSON"""
        import json
        from dataclasses import asdict

        data = asdict(obj)

        if include_base_info:
            data["base_info"] = {"channel_version": self._channel_version}

        # Remove None values
        data = {k: v for k, v in data.items() if v is not None}

        return json.dumps(data)

    def _json_to_get_updates_resp(self, raw: str) -> GetUpdatesResp:
        """Parse getUpdates response"""
        import json
        data = json.loads(raw)

        msgs = []
        for msg_data in data.get("msgs", []):
            msg = self._dict_to_message(msg_data)
            msgs.append(msg)

        return GetUpdatesResp(
            ret=data.get("ret", 0),
            errcode=data.get("errcode"),
            errmsg=data.get("errmsg"),
            msgs=msgs,
            get_updates_buf=data.get("get_updates_buf", ""),
            longpolling_timeout_ms=data.get("longpolling_timeout_ms"),
        )

    def _json_to_get_upload_url_resp(self, raw: str) -> GetUploadUrlResp:
        """Parse getUploadUrl response"""
        import json
        data = json.loads(raw)
        return GetUploadUrlResp(
            upload_param=data.get("upload_param"),
            thumb_upload_param=data.get("thumb_upload_param"),
        )

    def _dict_to_message(self, data: Dict) -> WeixinMessage:
        """Convert dict to WeixinMessage"""
        from .types import (
            ImageItem, VideoItem, FileItem, VoiceItem,
            CDNMedia
        )

        item_list = []
        for item_data in data.get("item_list", []):
            item = MessageItem(
                type=item_data.get("type", 0),
                msg_id=item_data.get("msg_id"),
            )

            if "text_item" in item_data:
                item.text_item = TextItem(text=item_data["text_item"].get("text"))

            if "image_item" in item_data:
                img = item_data["image_item"]
                item.image_item = ImageItem(
                    media=CDNMedia(**img.get("media", {})) if "media" in img else None,
                    mid_size=img.get("mid_size"),
                )

            if "video_item" in item_data:
                vid = item_data["video_item"]
                item.video_item = VideoItem(
                    media=CDNMedia(**vid.get("media", {})) if "media" in vid else None,
                    video_size=vid.get("video_size"),
                )

            if "file_item" in item_data:
                f = item_data["file_item"]
                item.file_item = FileItem(
                    media=CDNMedia(**f.get("media", {})) if "media" in f else None,
                    file_name=f.get("file_name"),
                    len=f.get("len"),
                )
            
            if "voice_item" in item_data:
                vo = item_data["voice_item"]
                item.voice_item = VoiceItem(
                    media=CDNMedia(**vo.get("media", {})) if "media" in vo else None,
                    encode_type=vo.get('encode_type'),
                    bits_per_sample=vo.get('bits_per_sample'),
                    sample_rate=vo.get('sample_rate'),
                    text=vo.get('text'),    
                    playtime=vo.get('playtime'),      
                )
            item_list.append(item)

        return WeixinMessage(
            seq=data.get("seq"),
            message_id=data.get("message_id"),
            from_user_id=data.get("from_user_id"),
            to_user_id=data.get("to_user_id"),
            client_id=data.get("client_id"),
            create_time_ms=data.get("create_time_ms"),
            session_id=data.get("session_id"),
            message_type=data.get("message_type", 0),
            message_state=data.get("message_state", 0),
            item_list=item_list,
            context_token=data.get("context_token"),
        )


import asyncio
