"""ErrorMapper — SDK 异常 → ProviderError 类型化映射。

三级匹配策略（按优先级）：
  1. 精确类型匹配 — isinstance 检查已知 SDK 异常类型
  2. status_code 回退 — 当异常对象有 status_code 属性时
  3. 消息关键词兜底 — 检查错误消息字符串中的关键词
"""
from agentd.providers.base import ErrorType, ProviderError


# ── 类型匹配表 ──────────────────────────────────────────────────
# 格式: (异常类名, ErrorType) — 按优先级排列
_TYPE_MAP: list[tuple[str, ErrorType]] = [
    ("RateLimitError",      ErrorType.RATE_LIMIT),
    ("AuthenticationError", ErrorType.AUTH_FAILURE),
    ("PermissionDeniedError", ErrorType.AUTH_FAILURE),
    ("InternalServerError", ErrorType.SERVER_ERROR),
    ("APITimeoutError",     ErrorType.TIMEOUT),
    ("NotFoundError",       ErrorType.MODEL_UNAVAILABLE),
]

# ── 消息关键词兜底表 ───────────────────────────────────────────
# 每个条目: (关键词列表, ErrorType) — 列表中 ALL 关键词必须同时出现
# 同一 ErrorType 的多个条目之间为 OR 关系
_KEYWORD_MAP: list[tuple[list[str], ErrorType]] = [
    (["rate", "limit"],              ErrorType.RATE_LIMIT),
    (["api key"],                    ErrorType.AUTH_FAILURE),
    (["auth"],                       ErrorType.AUTH_FAILURE),
    (["unauthorized"],               ErrorType.AUTH_FAILURE),
    (["forbidden"],                  ErrorType.AUTH_FAILURE),
    (["timeout"],                    ErrorType.TIMEOUT),
    (["timed", "out"],               ErrorType.TIMEOUT),
    (["context", "token"],           ErrorType.CONTEXT_OVERFLOW),
    (["token", "limit"],             ErrorType.CONTEXT_OVERFLOW),
    (["context", "length"],          ErrorType.CONTEXT_OVERFLOW),
    (["model", "not found"],         ErrorType.MODEL_UNAVAILABLE),
    (["model", "unavailable"],       ErrorType.MODEL_UNAVAILABLE),
    (["internal", "server"],         ErrorType.SERVER_ERROR),
    (["service", "unavailable"],     ErrorType.SERVER_ERROR),
]


def classify(exc: Exception) -> ProviderError:
    """将 SDK 异常映射为类型化 ProviderError。

    已分类的 ProviderError 直接透传。
    三级匹配：
      1. 精确类型匹配（类名包含已知 SDK 异常名）
      2. status_code 匹配（针对有 status_code 属性的异常）
      3. 消息关键词兜底（针对非标准 provider）
    全部不匹配则返回 UNKNOWN。
    """
    # 已分类的 ProviderError 直接透传
    if isinstance(exc, ProviderError):
        return exc

    msg = str(exc)
    status_code = getattr(exc, "status_code", 0) or 0
    exc_type_name = type(exc).__name__

    # Level 1: 精确类型匹配
    for sdk_name, error_type in _TYPE_MAP:
        if sdk_name in exc_type_name or sdk_name.lower() in exc_type_name.lower():
            return ProviderError(error_type, msg, status_code=status_code, original=exc)

    # Context overflow 特殊处理: BadRequestError + context_length
    if status_code == 400 and ("context" in msg.lower() or "token" in msg.lower()):
        return ProviderError(ErrorType.CONTEXT_OVERFLOW, msg, status_code=status_code, original=exc)
    if status_code == 400 and ("BadRequest" in exc_type_name or "bad request" in exc_type_name.lower()):
        if "context" in msg.lower() or "token" in msg.lower() or "length" in msg.lower():
            return ProviderError(ErrorType.CONTEXT_OVERFLOW, msg, status_code=status_code, original=exc)

    # Level 2: status_code 回退
    if status_code == 429:
        return ProviderError(ErrorType.RATE_LIMIT, msg, status_code=status_code, original=exc)
    if status_code in (401, 403):
        return ProviderError(ErrorType.AUTH_FAILURE, msg, status_code=status_code, original=exc)
    if status_code >= 500:
        return ProviderError(ErrorType.SERVER_ERROR, msg, status_code=status_code, original=exc)
    if status_code == 404:
        return ProviderError(ErrorType.MODEL_UNAVAILABLE, msg, status_code=status_code, original=exc)
    if status_code == 408:
        return ProviderError(ErrorType.TIMEOUT, msg, status_code=status_code, original=exc)

    # Level 3: 消息关键词兜底
    msg_lower = msg.lower()
    for keywords, error_type in _KEYWORD_MAP:
        if all(kw in msg_lower for kw in keywords):
            return ProviderError(error_type, msg, status_code=status_code, original=exc)

    # 无法识别
    return ProviderError(ErrorType.UNKNOWN, msg, status_code=status_code, original=exc)
