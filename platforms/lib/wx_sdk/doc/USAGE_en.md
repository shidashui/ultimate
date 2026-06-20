# Weixin Bot Python SDK Documentation

[简体中文](USAGE.md) | English

## Project Structure

```
weixin-clawbot-python/
├── pyproject.toml          # Project configuration
├── README.md               # Project documentation
├── app/
│   ├── __init__.py         # Package entry
│   ├── bot.py              # Main Bot class
│   ├── auth.py             # Authentication and login
│   ├── api.py              # API client
│   ├── monitor.py          # Message monitoring
│   ├── storage.py          # Storage management
│   ├── cdn.py              # CDN upload
│   ├── types.py            # Type definitions
│   ├── utils.py            # Utility functions
│   └── exceptions.py       # Exception definitions
├── examples/
│   ├── echo_bot.py         # Echo bot example
│   └── send_media.py       # Send media example
└── tests/                  # Test directory
```

## Core Classes

### WeixinBot

Main entry class that encapsulates all functionality.

```python
bot = WeixinBot(
    config=BotConfig(...),      # Optional configuration
    storage_path="~/.weixin-clawbot"  # Optional storage path
)
```

### Login Flow

```python
# QR code login
await bot.login(timeout_ms=480000, verbose=True)

# Or use existing token
await bot.login_with_token(account_id, token)

# Or load saved account
await bot.load_saved_account()
```

### Setting Callbacks

```python
# Message callback (required)
@bot.on_message
async def handle_message(message: WeixinMessage):
    print(f"Received: {message}")

# Error callback (optional)
@bot.on_error
async def handle_error(error: Exception):
    print(f"Error: {error}")

# Status callback (optional)
@bot.on_status
async def handle_status(status: str):
    print(f"Status: {status}")
```

### Sending Messages

```python
# Send text
await bot.send_text(
    to="user@im.wechat",
    text="Hello!"
)

# Send image
await bot.send_image(
    to="user@im.wechat",
    file_path="/path/to/image.png",
    text="Caption"
)

# Send video
await bot.send_video(
    to="user@im.wechat",
    file_path="/path/to/video.mp4",
    text="Caption"
)

# Send file
await bot.send_file(
    to="user@im.wechat",
    file_path="/path/to/file.pdf",
    text="Attachment"
)
```

### Start Monitoring

```python
# Blocking run
await bot.start()

# Or run in a new task
asyncio.create_task(bot.start())

# Stop
await bot.stop()
```

## Full Example

See `examples/echo_bot.py`

## Configuration Options

```python
BotConfig(
    base_url="https://ilinkai.weixin.qq.com",       # API base URL
    cdn_base_url="https://novac2c.cdn.weixin.qq.com/c2c",  # CDN base URL
    bot_type="3",                                     # Bot type
    long_poll_timeout_ms=35000,                       # Long polling timeout
    max_consecutive_failures=3,                       # Max consecutive failures
    backoff_delay_ms=30000,                           # Backoff delay
    retry_delay_ms=2000,                              # Retry delay
    session_pause_duration_ms=3600000,                # Session pause duration (1 hour)
)
```

## Message Types

```python
class MessageItemType(IntEnum):
    TEXT = 1   # Text
    IMAGE = 2  # Image
    VOICE = 3  # Voice
    FILE = 4   # File
    VIDEO = 5  # Video
```

## Storage Location

Default storage is in `~/.weixin-clawbot/`:

```
~/.weixin-clawbot/
├── accounts.json              # Account index
└── accounts/
    ├── {account_id}.json      # Account data (token, base_url)
    └── {account_id}.sync.json # Sync cursor
```

## Error Handling

```python
from app.exceptions import (
    LoginError,           # Login failed
    SessionExpiredError,  # Session expired (-14)
    APIError,             # API error
    NetworkError,         # Network error
    UploadError,          # Upload error
)

try:
    await bot.login()
except LoginError as e:
    print(f"Login failed: {e}")
```
