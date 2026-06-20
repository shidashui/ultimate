# Weixin ClawBot Python

[简体中文](README.md) | English 

Python implementation of the openclaw-weixin.

[![GitHub](https://img.shields.io/badge/GitHub-er1cw00/weixin--clawbot--python-blue)](https://github.com/er1cw00/weixin-clawbot-python)

## Features

### Authentication
- **QR Code Login** - Login with QR code scanning, with automatic refresh
- **Token Persistence** - Save/load account credentials and sync buffers in `~/.weixin-clawbot` by default

### Messaging
   
| Status | Feature | Description |
|--------|---------|-------------|
| ✅ | Receive Messages | Long-poll message monitoring for incoming messages |
| ✅ | Receive Image | Download and decrypt received images |
| ✅ | Receive Video | Download and decrypt received videos |
| ✅ | Receive File | Download and decrypt received files |
| ✅ | Receive Voice | Download voice messages with SILK to WAV transcoding |
| ✅ | Send Text | Send plain text messages |
| ✅ | Send Image | Send image files (JPG, PNG, etc.) |
| ✅ | Send Video | Send video files (MP4, etc.) |
| ✅ | Send File | Send file attachments (PDF, DOC, etc.) |
| ✅ | Send Typing | Send Typing indicator |



## Installation

```bash
pip install git+https://github.com/er1cw00/weixin-clawbot-python.git
```

Or clone and install locally:

```bash
git clone https://github.com/er1cw00/weixin-clawbot-python.git
cd weixin-clawbot-python
pip install -e .
```

## Quick Start

```python
import asyncio
from app.bot import WeixinBot

async def main():
    bot = WeixinBot()

    # Set up message handler
    @bot.on_message
    async def handle_message(message):
        print(f"From: {message.from_user_id}")
        print(f"Content: {message.item_list}")

        # Reply
        await bot.send_text(
            to=message.from_user_id,
            text="Hello! Received your message."
        )

    if not await bot.load_saved_account():
        print("Starting QR login...")
        success = await bot.login(verbose=True)
        if not success:
            print("Login failed")
            return

    # Start monitoring (blocking)
    await bot.start()

if __name__ == "__main__":
    asyncio.run(main())
```


## Example

Run the included echo bot example:

```bash
python examples/echo_bot.py
```

This will:
1. Display a QR code for Weixin login
2. Start monitoring for incoming messages
3. Echo back any received text messages
4. Save received media files (images, videos, files, voice) to `~/.weixin-clawbot/received_media/`
5. **Note:** The bot can only reply after receiving a message (to obtain `context_token`). It cannot proactively send messages before that.

The echo bot also supports commands:
- `/send_image` - Sends `examples/example.jpg`
- `/send_video` - Sends `examples/example.mp4`
- `/send_file` - Sends `examples/example.md`

## API Reference

See [doc/USAGE_en.md](doc/USAGE_en.md) for detailed API documentation.

## License

MIT
