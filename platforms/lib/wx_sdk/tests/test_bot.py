"""
Tests for Weixin Bot
"""

import pytest
import asyncio

from ..app.types import WeixinMessage, MessageItem, TextItem, MessageItemType
from ..app.utils import markdown_to_plain_text, aes_ecb_padded_size


class TestUtils:
    """Test utility functions"""

    def test_markdown_to_plain_text_code_block(self):
        text = "```python\nprint('hello')\n```"
        result = markdown_to_plain_text(text)
        assert "print('hello')" in result
        assert "```" not in result

    def test_markdown_to_plain_text_image(self):
        text = "Hello ![alt](url) world"
        result = markdown_to_plain_text(text)
        assert "Hello" in result
        assert "world" in result
        assert "![alt]" not in result

    def test_markdown_to_plain_text_link(self):
        text = "Click [here](http://example.com) now"
        result = markdown_to_plain_text(text)
        assert "Click" in result
        assert "here" in result
        assert "now" in result
        assert "http" not in result

    def test_markdown_to_plain_text_bold(self):
        text = "This is **bold** text"
        result = markdown_to_plain_text(text)
        assert "This is bold text" == result

    def test_aes_ecb_padded_size(self):
        assert aes_ecb_padded_size(16) == 16
        assert aes_ecb_padded_size(17) == 32
        assert aes_ecb_padded_size(32) == 32
        assert aes_ecb_padded_size(33) == 48


class TestTypes:
    """Test type definitions"""

    def test_weixin_message_creation(self):
        msg = WeixinMessage(
            from_user_id="user@im.wechat",
            to_user_id="bot@im.bot",
            message_type=1,
            item_list=[
                MessageItem(
                    type=MessageItemType.TEXT,
                    text_item=TextItem(text="Hello")
                )
            ]
        )
        assert msg.from_user_id == "user@im.wechat"
        assert len(msg.item_list) == 1
        assert msg.item_list[0].type == MessageItemType.TEXT


class TestBot:
    """Test Bot class"""

    @pytest.mark.asyncio
    async def test_bot_creation(self):
        from app.bot import WeixinBot
        bot = WeixinBot()
        assert bot is not None
        assert not bot.is_logged_in

    @pytest.mark.asyncio
    async def test_message_callback(self):
        from app.bot import WeixinBot
        bot = WeixinBot()

        messages = []

        @bot.on_message
        async def handler(msg):
            messages.append(msg)

        # Simulate message
        test_msg = WeixinMessage(from_user_id="test")
        await bot._notify_message(test_msg)

        assert len(messages) == 1
        assert messages[0].from_user_id == "test"
