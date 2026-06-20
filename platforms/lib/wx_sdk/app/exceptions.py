"""
Custom exceptions
"""


class WeixinBotError(Exception):
    """Base exception for Weixin Bot"""
    pass


class LoginError(WeixinBotError):
    """Login failed"""
    pass


class SessionExpiredError(WeixinBotError):
    """Session expired (error code -14)"""
    pass


class APIError(WeixinBotError):
    """API call failed"""
    def __init__(self, message: str, ret: int = 0, errcode: int = 0):
        super().__init__(message)
        self.ret = ret
        self.errcode = errcode


class NetworkError(WeixinBotError):
    """Network error"""
    pass


class UploadError(WeixinBotError):
    """File upload failed"""
    pass
