import argparse
import subprocess
import os
import asyncio
from config.logging_config import setup_logging
setup_logging()

PID_FILE = "agentd.pid"
HOST = "127.0.0.1"
PORT = 8765

def start_cmd():
    print("服务已启动")
    process = subprocess.Popen(["python", "app.py"])
    with open(PID_FILE, "w") as f:
        f.write(str(process.pid))
    print(f"进程号: {process.pid}")

def stop_cmd():
    print("服务已停止")
    if os.path.exists(PID_FILE):
        with open(PID_FILE, "r") as f:
            pid = int(f.read())
            try:
                os.kill(pid, 9)
                print(f"已杀死进程 {pid}")
            except ProcessLookupError:
                print(f"进程 {pid} 不存在")
        os.remove(PID_FILE)
    else:
        print("没有找到进程文件 process.pid")

def interactive_cmd():
    from cli.cli import Cli
    cli = Cli()
    cli.run()

async def gateway_cmd(args=None):
    from platforms.voice import VoicePlatform
    from gateway import Gateway
    from gateway.tauri_platform import TauriPlatform

    # ── Tauri 子进程 ──
    tauri_process = None
    no_gui = args and getattr(args, 'no_gui', False)

    if not no_gui:
        tauri_bin = _find_tauri_binary()
        if tauri_bin:
            try:
                tauri_process = subprocess.Popen([tauri_bin], creationflags=subprocess.CREATE_NO_WINDOW)
                print(f"[Gateway] Tauri App started (PID: {tauri_process.pid})")
            except Exception as e:
                print(f"[Gateway] Warning: Failed to start Tauri: {e}")
        else:
            print("[Gateway] Warning: Tauri binary not found, running without GUI")

    # ── 注册平台 ──
    tauri_plat = TauriPlatform(port=18765)
    voice_plat = VoicePlatform(wake_word="你好")
    voice_plat.set_tauri_platform(tauri_plat)

    gateway = Gateway().register(tauri_plat).register(voice_plat)

    try:
        await gateway.run()
    except KeyboardInterrupt:
        pass
    finally:
        await gateway.stop()
        if tauri_process:
            tauri_process.terminate()
            try:
                tauri_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                tauri_process.kill()
            print("[Gateway] Tauri App stopped")


def _find_tauri_binary() -> str | None:
    """查找 Tauri 二进制文件。"""
    for candidate in [
        os.path.join("ui", "src-tauri", "target", "release", "jarvis-ui.exe"),
        os.path.join("ui", "src-tauri", "target", "debug", "jarvis-ui.exe"),
    ]:
        if os.path.isfile(candidate):
            return os.path.abspath(candidate)
    try:
        import shutil
        return shutil.which("jarvis-ui")
    except Exception:
        return None


def main():
    parser = argparse.ArgumentParser(prog="ultimate", description="Ultimate CLI")

    parser.add_argument(
        "command",
        choices=["help", "start", "stop", "chat", "gateway"],
        help="命令"
    )
    parser.add_argument("--no-gui", action="store_true", help="Disable Tauri GUI (only for gateway)")

    args = parser.parse_args()

    if args.command == "help":
        print(
            "命令列表：\n"
            "  help      显示帮助信息\n"
            "  start     启动服务\n"
            "  stop      停止服务\n"
            "  chat      进入交互模式\n"
            "  gateway   启动消息网关\n")
    elif args.command == "start":
        start_cmd()
    elif args.command == "stop":
        stop_cmd()
    elif args.command == "chat":
        interactive_cmd()
    elif args.command == "gateway":
        asyncio.run(gateway_cmd(args))

if __name__ == "__main__":
    main()
