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

async def gateway_cmd():
    from platforms.weixin import WeChatPlatform
    from platforms.voice import VoicePlatform
    from gateway import Gateway
    gateway = (
        Gateway().register(VoicePlatform(wake_word="你好")) 
                #  .register(WeChatPlatform())
    )

    try:
        await gateway.run()
    except KeyboardInterrupt:
        pass
    finally:
        await gateway.stop()

def main():
    parser = argparse.ArgumentParser(prog="ultimate", description="Ultimate CLI")

    parser.add_argument(
        "command",
        choices=["help", "start", "stop", "chat", "gateway"],
        help="命令"
    )

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
        asyncio.run(gateway_cmd())

if __name__ == "__main__":
    main()