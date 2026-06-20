# Weixin Bot Python SDK 文档

简体中文 | [English](USAGE_en.md)

## 项目结构

```
weixin-clawbot-python/
├── pyproject.toml          # 项目配置
├── README.md               # 项目说明
├── app/
│   ├── __init__.py         # 包入口
│   ├── bot.py              # 主 Bot 类
│   ├── auth.py             # 认证和登录
│   ├── api.py              # API 客户端
│   ├── monitor.py          # 消息监控
│   ├── storage.py          # 存储管理
│   ├── cdn.py              # CDN 上传
│   ├── types.py            # 类型定义
│   ├── utils.py            # 工具函数
│   └── exceptions.py       # 异常定义
├── examples/
│   ├── echo_bot.py         # 回显机器人示例
│   └── send_media.py       # 发送媒体示例
└── tests/                  # 测试目录
```

## 核心类

### WeixinBot

主入口类，封装了所有功能。

```python
bot = WeixinBot(
    config=BotConfig(...),      # 可选配置
    storage_path="~/.weixin-clawbot"  # 可选存储路径
)
```

### 登录流程

```python
# QR 码登录
await bot.login(timeout_ms=480000, verbose=True)

# 或使用已有 token
await bot.login_with_token(account_id, token)

# 或加载保存的账号
await bot.load_saved_account()
```

### 设置回调

```python
# 消息回调 (必需)
@bot.on_message
async def handle_message(message: WeixinMessage):
    print(f"Received: {message}")

# 错误回调 (可选)
@bot.on_error
async def handle_error(error: Exception):
    print(f"Error: {error}")

# 状态回调 (可选)
@bot.on_status
async def handle_status(status: str):
    print(f"Status: {status}")
```

### 发送消息

```python
# 发送文本
await bot.send_text(
    to="user@im.wechat",
    text="Hello!"
)

# 发送图片
await bot.send_image(
    to="user@im.wechat",
    file_path="/path/to/image.png",
    text="Caption"
)

# 发送视频
await bot.send_video(
    to="user@im.wechat",
    file_path="/path/to/video.mp4",
    text="Caption"
)

# 发送文件
await bot.send_file(
    to="user@im.wechat",
    file_path="/path/to/file.pdf",
    text="Attachment"
)
```

### 启动监控

```python
# 阻塞运行
await bot.start()

# 或在新任务中运行
asyncio.create_task(bot.start())

# 停止
await bot.stop()
```

## 完整示例

见 `examples/echo_bot.py`

## 配置选项

```python
BotConfig(
    base_url="https://ilinkai.weixin.qq.com",       # API 基础 URL
    cdn_base_url="https://novac2c.cdn.weixin.qq.com/c2c",  # CDN 基础 URL
    bot_type="3",                                     # Bot 类型
    long_poll_timeout_ms=35000,                       # 长轮询超时
    max_consecutive_failures=3,                       # 最大连续失败次数
    backoff_delay_ms=30000,                           # 退避延迟
    retry_delay_ms=2000,                              # 重试延迟
    session_pause_duration_ms=3600000,                # Session 暂停时长 (1小时)
)
```

## 消息类型

```python
class MessageItemType(IntEnum):
    TEXT = 1   # 文本
    IMAGE = 2  # 图片
    VOICE = 3  # 语音
    FILE = 4   # 文件
    VIDEO = 5  # 视频
```

## 存储位置

默认存储在 `~/.weixin-clawbot/`:

```
~/.weixin-clawbot/
├── accounts.json              # 账号索引
└── accounts/
    ├── {account_id}.json      # 账号数据 (token, base_url)
    └── {account_id}.sync.json # 同步游标
```

## 错误处理

```python
from app.exceptions import (
    LoginError,           # 登录失败
    SessionExpiredError,  # Session 过期 (-14)
    APIError,             # API 错误
    NetworkError,         # 网络错误
    UploadError,          # 上传错误
)

try:
    await bot.login()
except LoginError as e:
    print(f"Login failed: {e}")
```
