"""
CDN upload utilities
"""

import logging
import hashlib
import secrets
from pathlib import Path
from urllib.parse import quote
import aiohttp

from .types import GetUploadUrlReq, GetUploadUrlResp, UploadedFileInfo, UploadMediaType
from .utils import aes_ecb_padded_size, aes_ecb_encrypt

logger = logging.getLogger(__name__)


class CdnUploader:
    """CDN file uploader"""

    def __init__(self, api):
        self.api = api

    async def upload_file(
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
            media_type: Media type

        Returns:
            UploadedFileInfo
        """
        # Read file
        path = Path(file_path)
        plaintext = path.read_bytes()
        rawsize = len(plaintext)

        # Calculate MD5
        rawfilemd5 = hashlib.md5(plaintext).hexdigest()

        # Calculate padded size for AES-128-ECB
        filesize = aes_ecb_padded_size(rawsize)

        # Generate random filekey and aeskey
        filekey = secrets.token_hex(16)
        aeskey = secrets.token_bytes(16)

        logger.debug(
            f"Upload: file={file_path} rawsize={rawsize} filesize={filesize} md5={rawfilemd5}"
        )

        # Get upload URL
        req = GetUploadUrlReq(
            filekey=filekey,
            media_type=media_type.value,
            to_user_id=to_user_id,
            rawsize=rawsize,
            rawfilemd5=rawfilemd5,
            filesize=filesize,
            no_need_thumb=True,
            aeskey=aeskey.hex(),
        )

        upload_url_resp = await self.api.get_upload_url(req)

        if not upload_url_resp.upload_param:
            raise ValueError("getUploadUrl returned no upload_param")

        # Upload to CDN
        download_param = await self._upload_to_cdn(
            buf=plaintext,
            upload_param=upload_url_resp.upload_param,
            filekey=filekey,
            cdn_base_url=self.api.config.cdn_base_url,
            aeskey=aeskey,
        )
        return UploadedFileInfo(
            filekey=filekey,
            download_encrypted_query_param=download_param,
            aeskey=aeskey.hex(),
            file_size=rawsize,
            file_size_ciphertext=filesize,
        )

    async def _upload_to_cdn(
        self,
        buf: bytes,
        upload_param: str,
        filekey: str,
        cdn_base_url: str,
        aeskey: bytes,
    ) -> str:
        """
        Upload buffer to CDN

        Args:
            buf: Plaintext buffer
            upload_param: Upload parameter from getUploadUrl
            filekey: File key
            cdn_base_url: CDN base URL
            aeskey: AES key

        Returns:
            Download encrypted query parameter
        """
        # Encrypt buffer
        encrypted = aes_ecb_encrypt(buf, aeskey)

        # Build CDN URL
        url = f"{cdn_base_url}/upload?encrypted_query_param={quote(upload_param, safe='')}&filekey={quote(filekey)}"
        logger.debug(f"Uploading to CDN: {url}")
        
        # Upload
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                data=encrypted,
                headers={
                    "Content-Type": "application/octet-stream",
                    "Content-Length": str(len(encrypted)),
                },
            ) as resp:
                if resp.status not in (200, 201):
                    body = await resp.text()
                    raise ValueError(f"CDN upload failed: {resp.status} {body}")

                # Parse response for download param
                response_text = await resp.text()
                logger.debug(f"CDN upload response: {response_text}")
                # for key, value in resp.headers.items():
                #     logger.debug(f"{key}: {value}")
                # logger.debug("# # # # # # #")
                encrypted_param = resp.headers.get("x-encrypted-param")
                return encrypted_param
        return ''
