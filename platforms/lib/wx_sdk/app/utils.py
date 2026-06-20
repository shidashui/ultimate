"""
Utility functions
"""

import re
import base64
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad


def markdown_to_plain_text(text: str) -> str:
    """
    Convert markdown to plain text

    - Code blocks: strip fences, keep content
    - Images: remove entirely
    - Links: keep display text only
    - Tables: convert pipes to spaces
    """
    result = text

    # Code blocks: ```lang\ncode\n``` -> code
    result = re.sub(r"```[^\n]*\n?([\s\S]*?)```", lambda m: m.group(1).strip(), result)

    # Images: ![alt](url) -> remove
    result = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", result)

    # Links: [text](url) -> text
    result = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", result)

    # Tables: remove separator rows
    result = re.sub(r"^\|[\s:|-]+\|$", "", result, flags=re.MULTILINE)

    # Tables: | a | b | -> "a  b"
    def replace_table_row(match):
        inner = match.group(1)
        cells = [cell.strip() for cell in inner.split("|")]
        return "  ".join(cells)

    result = re.sub(r"^\|(.+)\|$", replace_table_row, result, flags=re.MULTILINE)

    # Bold/italic: **text** or *text* -> text
    result = re.sub(r"\*\*([^*]+)\*\*", r"\1", result)
    result = re.sub(r"\*([^*]+)\*", r"\1", result)

    # Headers: ### text -> text
    result = re.sub(r"^#+\s*", "", result, flags=re.MULTILINE)

    return result.strip()


def parse_aes_key(aes_key_base64: str) -> bytes:
    try:
        # 1. Base64 解码
        decoded = base64.b64decode(aes_key_base64)
    except Exception:
        msg = f"Invalid base64 string provided"
        raise ValueError(msg)

    # 情况 A: 解码后直接是 16 字节原始数据 (AES-128)
    if len(decoded) == 16:
        return decoded

    # 情况 B: 解码后是 32 字节，且内容是十六进制字符串 (32位 Hex)
    if len(decoded) == 32:
        try:
            # 将字节转为 ascii 字符串进行正则匹配
            decoded_str = decoded.decode('ascii')
            if re.fullmatch(r'[0-9a-fA-F]{32}', decoded_str):
                # hex-encoded key: base64 -> hex string -> raw bytes
                return bytes.fromhex(decoded_str)
        except (UnicodeDecodeError, ValueError):
            # 如果不是合法的 ascii 或 hex，记录错误并下行抛出异常
            pass

    # 错误处理
    msg = (f"aes_key must decode to 16 raw bytes or 32-char hex string, "
           f"got {len(decoded)} bytes (base64='{aes_key_base64}')")

    raise ValueError(msg)

def aes_ecb_padded_size(raw_size: int) -> int:
    block_size = 16
    # 无论是否对齐，都至少填充 1 字节，最多填充 16 字节
    return (raw_size // block_size + 1) * block_size

def aes_ecb_encrypt(plaintext: bytes, key: bytes) -> bytes:
    """
    Encrypt with AES-128-ECB

    Args:
        plaintext: Plaintext bytes
        key: 16-byte AES key

    Returns:
        Ciphertext bytes
    """
    cipher = AES.new(key, AES.MODE_ECB)
    padded = pad(plaintext, AES.block_size)
    return cipher.encrypt(padded)


def aes_ecb_decrypt(ciphertext: bytes, key: bytes) -> bytes:
    """
    Decrypt with AES-128-ECB

    Args:
        ciphertext: Ciphertext bytes
        key: 16-byte AES key

    Returns:
        Plaintext bytes
    """
    from Crypto.Util.Padding import unpad

    cipher = AES.new(key, AES.MODE_ECB)
    padded = cipher.decrypt(ciphertext)
    return unpad(padded, AES.block_size)
