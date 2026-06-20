"""
Example: Basic bot with QR login and message echo
Saves received media files (image, video, voice, file) to local directory
"""

import asyncio
import logging
from pathlib import Path

from platforms.lib.wx_sdk.app.bot import WeixinBot, MediaInfo
from platforms.lib.wx_sdk.app.types import MessageItemType, TypingStatus
from config.configs import WORKDIR

# Enable logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s.%(msecs)03d %(levelname)s %(filename)s:%(lineno)d %(message)s",
    datefmt="%H:%M:%S"
)

# Directory to save received media files
MEDIA_SAVE_DIR = WORKDIR / ".weixin-clawbot" / "received_media"


async def main():
    bot = WeixinBot(storage_path=str(MEDIA_SAVE_DIR))

    # Status updates
    @bot.on_status
    async def on_status(message: str):
        print(f"[Status] {message}")

    # Error handling
    @bot.on_error
    async def on_error(error: Exception):
        print(f"[Error] {error}")

    # Message handler
    @bot.on_message
    async def on_message(message):
        print(f"\n{'='*50}")
        print(f"New message from: {message.from_user_id}")
        print(f"Session: {message.session_id}")
        print(f"Context Token: {message.context_token}")

        # Process message using process_message function
        text, media_info = await bot.process_message(
            message,
            save_dir=str(MEDIA_SAVE_DIR)
        )

        if text:
            print(f"Text: {text}")

            # Handle commands
            if text.startswith("/send_image"):
                if message.from_user_id and message.context_token:
                    print("[Command] Sending image...")
                    await bot.send_image(
                        to=message.from_user_id,
                        file_path="examples/example.jpg",
                        text="Here's an example image"
                    )
                return

            elif text.startswith("/send_video"):
                if message.from_user_id and message.context_token:
                    print("[Command] Sending video...")
                    await bot.send_video(
                        to=message.from_user_id,
                        file_path="examples/example.mp4",
                        text="Here's an example video"
                    )
                return

            elif text.startswith("/send_file"):
                if message.from_user_id and message.context_token:
                    print("[Command] Sending file...")
                    await bot.send_file(
                        to=message.from_user_id,
                        file_path="examples/example.md",
                        text="Here's an example file"
                    )
                return

            elif text.startswith("/typing"):
                if message.from_user_id:
                    print("[Command] Sending typing indicator...")
                    # Get config to obtain typing_ticket
                    config = await bot.get_config(message.from_user_id)
                    if config.typing_ticket:
                        await bot.send_typing(
                            to=message.from_user_id,
                            typing_ticket=config.typing_ticket,
                            status=TypingStatus.TYPING
                        )
                        print("[Command] Typing indicator sent")
                    else:
                        print("[Command] No typing ticket available")
                return

            elif text.startswith("/cancel"):
                if message.from_user_id:
                    print("[Command] Sending cancel typing...")
                    # Get config to obtain typing_ticket
                    config = await bot.get_config(message.from_user_id)
                    if config.typing_ticket:
                        await bot.send_typing(
                            to=message.from_user_id,
                            typing_ticket=config.typing_ticket,
                            status=TypingStatus.CANCEL
                        )
                        print("[Command] Cancel typing sent")
                    else:
                        print("[Command] No typing ticket available")
                return

            # Echo back text (only if not a command)
            if message.from_user_id and message.context_token:
                await bot.send_text(
                    to=message.from_user_id,
                    text=f"Echo: {text}"
                )

        if media_info:
            type_name = MessageItemType(media_info.type).name
            print(f"[{type_name} received]")
            print(f"  File: {media_info.file_name}")
            print(f"  Path: {media_info.file_path}")
            print(f"  Size: {media_info.file_size} bytes")

            # Echo back media info
            if message.from_user_id and message.context_token:
                await bot.send_text(
                    to=message.from_user_id,
                    text=f"Received {type_name}: {media_info.file_name} ({media_info.file_size} bytes)"
                )

        print(f"{'='*50}\n")

    # Try to load saved account first
    if await bot.load_saved_account():
        print("Loaded saved account")
    else:
        # Do QR login
        print("Starting QR login...")
        success = await bot.login(verbose=True)
        if not success:
            print("Login failed")
            return

    print(f"\nBot is running. Media files will be saved to: {MEDIA_SAVE_DIR}")
    print("Press Ctrl+C to stop.\n")

    try:
        await bot.start()
    except KeyboardInterrupt:
        print("\nStopping...")
        await bot.stop()


if __name__ == "__main__":
    print(MEDIA_SAVE_DIR)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExited")
