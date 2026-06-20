"""
Type definitions for Weixin Bot API
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from enum import IntEnum


class MessageItemType(IntEnum):
    NONE = 0
    TEXT = 1
    IMAGE = 2
    VOICE = 3
    FILE = 4
    VIDEO = 5


class MessageType(IntEnum):
    NONE = 0
    USER = 1
    BOT = 2


class MessageState(IntEnum):
    NEW = 0
    GENERATING = 1
    FINISH = 2


class UploadMediaType(IntEnum):
    IMAGE = 1
    VIDEO = 2
    FILE = 3
    VOICE = 4


class TypingStatus(IntEnum):
    TYPING = 1
    CANCEL = 2


@dataclass
class CDNMedia:
    """CDN media reference"""
    encrypt_query_param: Optional[str] = None
    aes_key: Optional[str] = None  # base64-encoded
    encrypt_type: Optional[int] = None  # 0=只加密fileid, 1=打包缩略图信息
    full_url: Optional[str] = None


@dataclass
class TextItem:
    text: Optional[str] = None


@dataclass
class ImageItem:
    media: Optional[CDNMedia] = None
    thumb_media: Optional[CDNMedia] = None
    aeskey: Optional[str] = None
    url: Optional[str] = None
    mid_size: Optional[int] = None
    thumb_size: Optional[int] = None
    thumb_height: Optional[int] = None
    thumb_width: Optional[int] = None
    hd_size: Optional[int] = None


@dataclass
class VoiceItem:
    media: Optional[CDNMedia] = None
    encode_type: Optional[int] = None  # 1=pcm, 2=adpcm, 6=silk
    bits_per_sample: Optional[int] = None
    sample_rate: Optional[int] = None
    playtime: Optional[int] = None  # milliseconds
    text: Optional[str] = None  # speech-to-text


@dataclass
class FileItem:
    media: Optional[CDNMedia] = None
    file_name: Optional[str] = None
    md5: Optional[str] = None
    len: Optional[str] = None


@dataclass
class VideoItem:
    media: Optional[CDNMedia] = None
    video_size: Optional[int] = None
    play_length: Optional[int] = None
    video_md5: Optional[str] = None
    thumb_media: Optional[CDNMedia] = None
    thumb_size: Optional[int] = None
    thumb_height: Optional[int] = None
    thumb_width: Optional[int] = None


@dataclass
class RefMessage:
    message_item: Optional[Any] = None
    title: Optional[str] = None


@dataclass
class MessageItem:
    type: int = 0
    create_time_ms: Optional[int] = None
    update_time_ms: Optional[int] = None
    is_completed: Optional[bool] = None
    msg_id: Optional[str] = None
    ref_msg: Optional[RefMessage] = None
    text_item: Optional[TextItem] = None
    image_item: Optional[ImageItem] = None
    voice_item: Optional[VoiceItem] = None
    file_item: Optional[FileItem] = None
    video_item: Optional[VideoItem] = None


@dataclass
class WeixinMessage:
    """Weixin message structure"""
    seq: Optional[int] = None
    message_id: Optional[int] = None
    from_user_id: Optional[str] = None
    to_user_id: Optional[str] = None
    client_id: Optional[str] = None
    create_time_ms: Optional[int] = None
    update_time_ms: Optional[int] = None
    delete_time_ms: Optional[int] = None
    session_id: Optional[str] = None
    group_id: Optional[str] = None
    message_type: int = 0
    message_state: int = 0
    item_list: List[MessageItem] = field(default_factory=list)
    context_token: Optional[str] = None


@dataclass
class BaseInfo:
    channel_version: Optional[str] = None


@dataclass
class GetUpdatesReq:
    get_updates_buf: str = ""
    base_info: Optional[BaseInfo] = None


@dataclass
class GetUpdatesResp:
    ret: int = 0
    errcode: Optional[int] = None
    errmsg: Optional[str] = None
    msgs: List[WeixinMessage] = field(default_factory=list)
    get_updates_buf: str = ""
    longpolling_timeout_ms: Optional[int] = None


@dataclass
class GetUploadUrlReq:
    filekey: Optional[str] = None
    media_type: Optional[int] = None
    to_user_id: Optional[str] = None
    rawsize: Optional[int] = None
    rawfilemd5: Optional[str] = None
    filesize: Optional[int] = None
    thumb_rawsize: Optional[int] = None
    thumb_rawfilemd5: Optional[str] = None
    thumb_filesize: Optional[int] = None
    no_need_thumb: Optional[bool] = None
    aeskey: Optional[str] = None


@dataclass
class GetUploadUrlResp:
    upload_param: Optional[str] = None
    thumb_upload_param: Optional[str] = None


@dataclass
class SendMessageReq:
    msg: Optional[WeixinMessage] = None


@dataclass
class SendMessageResp:
    pass


@dataclass
class SendTypingReq:
    ilink_user_id: Optional[str] = None
    typing_ticket: Optional[str] = None
    status: int = 1


@dataclass
class SendTypingResp:
    ret: int = 0
    errmsg: Optional[str] = None


@dataclass
class GetConfigResp:
    ret: int = 0
    errmsg: Optional[str] = None
    typing_ticket: Optional[str] = None


@dataclass
class QRCodeResponse:
    """QR code response from get_bot_qrcode"""
    qrcode: str
    qrcode_img_content: str


@dataclass
class StatusResponse:
    """Status response from get_qrcode_status"""
    status: str  # "wait" | "scaned" | "confirmed" | "expired"
    bot_token: Optional[str] = None
    ilink_bot_id: Optional[str] = None
    baseurl: Optional[str] = None
    ilink_user_id: Optional[str] = None


@dataclass
class LoginStartResult:
    """Result of starting login"""
    qrcode_url: Optional[str]
    message: str
    session_key: str


@dataclass
class LoginWaitResult:
    """Result of waiting for login"""
    connected: bool
    bot_token: Optional[str] = None
    account_id: Optional[str] = None
    base_url: Optional[str] = None
    user_id: Optional[str] = None
    message: str = ""


@dataclass
class UploadedFileInfo:
    """Information about uploaded file"""
    filekey: str
    download_encrypted_query_param: str
    aeskey: str  # hex-encoded
    file_size: int
    file_size_ciphertext: int
