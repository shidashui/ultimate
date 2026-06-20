# Weixin ClawBot Python

简体中文 | [English](README_en.md) 

openclaw-weixin 的 Python 实现.

[![GitHub](https://img.shields.io/badge/GitHub-er1cw00/weixin--clawbot--python-blue)](https://github.com/er1cw00/weixin-clawbot-python)

## 功能特性

### 认证
- **二维码登录** - 扫描二维码登录，支持自动刷新
- **Token 持久化** - 默认在 `~/.weixin-clawbot` 保存/加载账号凭证和同步缓冲区

### 消息功能

| 状态 | 功能 | 说明 |
|------|------|------|
| ✅ | 接收消息 | 长轮询监控 incoming 消息 |
| ✅ | 接收图片 | 下载并解密接收到的图片 |
| ✅ | 接收视频 | 下载并解密接收到的视频 |
| ✅ | 接收文件 | 下载并解密接收到的文件 |
| ✅ | 接收语音 | 下载语音消息并 SILK 转 WAV |
| ✅ | 发送文本 | 发送纯文本消息 |
| ✅ | 发送图片 | 发送图片文件 (JPG, PNG 等) |
| ✅ | 发送视频 | 发送视频文件 (MP4 等) |
| ✅ | 发送文件 | 发送文件附件 (PDF, DOC 等) |
| ✅ | 发送输入中 | 发送"正在输入"状态 |

## 安装

```bash
pip install git+https://github.com/er1cw00/weixin-clawbot-python.git
```

或者克隆到本地安装：

```bash
git clone https://github.com/er1cw00/weixin-clawbot-python.git
cd weixin-clawbot-python
pip install -e .
```

## 快速开始

```python
import asyncio
from app.bot import WeixinBot

async def main():
    bot = WeixinBot()

    # 设置消息处理器
    @bot.on_message
    async def handle_message(message):
        print(f"来自: {message.from_user_id}")
        print(f"内容: {message.item_list}")

        # 回复
        await bot.send_text(
            to=message.from_user_id,
            text="你好！已收到你的消息。"
        )

    # 二维码登录
    if not await bot.load_saved_account():
        print("Starting QR login...")
        success = await bot.login(verbose=True)
        if not success:
            print("Login failed")
            return

    # 开始监听 (阻塞)
    await bot.start()

if __name__ == "__main__":
    asyncio.run(main())
```


## 示例

运行自带的 echo bot 示例：

```bash
python examples/echo_bot.py
```

功能说明：
1. 显示微信登录二维码
2. 开始监听消息
3. 自动回复收到的文本消息
4. 将接收到的媒体文件（图片、视频、文件、语音）保存到 `~/.weixin-clawbot/received_media/`
5. **注意：** Bot 需要先收到用户消息获取 `context_token` 后才能回复，无法主动发送消息

echo bot 还支持以下命令：
- `/send_image` - 发送 `examples/example.jpg`
- `/send_video` - 发送 `examples/example.mp4`
- `/send_file` - 发送 `examples/example.md`

## API 文档

详细 API 文档请参考 [doc/USAGE.md](doc/USAGE.md)。

## 许可证

MIT
