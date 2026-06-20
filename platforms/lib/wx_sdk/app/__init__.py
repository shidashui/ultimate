"""
Weixin Bot - Python SDK for Weixin Bot API
"""

from .bot import WeixinBot, BotConfig, MediaInfo
from .types import (
    WeixinMessage,
    MessageItem,
    MessageItemType,
    TextItem,
    ImageItem,
    VideoItem,
    FileItem,
    VoiceItem,
    CDNMedia,
    GetUpdatesResp,
    SendMessageReq,
)
from .auth import WeixinAuth
from .monitor import MessageMonitor
from .exceptions import (
    WeixinBotError,
    LoginError,
    SessionExpiredError,
    APIError,
)

__version__ = "0.1.0"
__all__ = [
    "WeixinBot",
    "BotConfig",
    "MediaInfo",
    "WeixinAuth",
    "MessageMonitor",
    "WeixinMessage",
    "MessageItem",
    "MessageItemType",
    "TextItem",
    "ImageItem",
    "VideoItem",
    "FileItem",
    "VoiceItem",
    "CDNMedia",
    "GetUpdatesResp",
    "SendMessageReq",
    "WeixinBotError",
    "LoginError",
    "SessionExpiredError",
    "APIError",
]
