"""VS Code F5 entry: initialize once, serve the dashboard, and open its login page."""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "dashboard"))


def find_cloudflared(explicit=None):
    local = PROJECT / "output" / "tools" / "cloudflared.exe"
    candidate = explicit or (str(local) if local.is_file() else shutil.which("cloudflared"))
    if not candidate or not Path(candidate).is_file():
        raise ValueError("未找到 cloudflared。可先选择不带“手机分享”的启动项进行本机使用。")
    return str(Path(candidate).resolve())


def tunnel_output(process, log_path, stopping):
    shared = False
    with log_path.open("w", encoding="utf-8") as log:
        for line in process.stdout:
            log.write(line)
            log.flush()
            found = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", line)
            if found and not shared:
                print("手机登录 / 注册链接：" + found.group() + "/login", flush=True)
                shared = True
    if process.wait() != 0 and not stopping.is_set():
        print(f"手机分享未能继续运行，本机网页仍可使用。分享日志：{log_path}", flush=True)


def stop_tunnel(process):
    if process is None:
        return
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def main(argv=None):
    parser = argparse.ArgumentParser(description="一键启动童域智枢网页")
    parser.add_argument("--share", action="store_true", help="同时生成手机可访问的 HTTPS 链接")
    parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    parser.add_argument("--port", type=int, default=int(os.environ.get("DASHBOARD_PORT", "8088")))
    parser.add_argument("--cloudflared", help="cloudflared 程序位置")
    args = parser.parse_args(argv)
    if not 1024 <= args.port <= 65535:
        parser.error("端口须在 1024–65535 之间")
    try:
        cloudflared = find_cloudflared(args.cloudflared) if args.share else None
        from manage_access import ensure_admin
        ensure_admin()
    except (ValueError, OSError) as exc:
        parser.exit(1, str(exc) + "\n")

    # Local preview uses an explicit development setting; sharing always uses Secure.
    os.environ["DASHBOARD_HOST"] = "127.0.0.1"
    os.environ["DASHBOARD_PORT"] = str(args.port)
    os.environ["DASHBOARD_COOKIE_SECURE"] = "1" if args.share else "0"
    import server

    process = None
    reader = None
    timer = None
    stopping = threading.Event()
    try:
        http = server.ThreadingHTTPServer(("127.0.0.1", args.port), server.Handler)
    except OSError:
        parser.exit(1, f"端口 {args.port} 已被占用，请停止之前运行的网页服务后再按 F5。\n")
    try:
        server.start_analysis_worker()
        login = f"http://127.0.0.1:{args.port}/login"
        print("网页已启动：" + login, flush=True)
        print("管理员登录后进入展示设置，普通用户登录后进入已开放的模块。", flush=True)
        if args.share:
            runtime = PROJECT / "output"
            runtime.mkdir(exist_ok=True)
            process = subprocess.Popen(
                [cloudflared, "tunnel", "--url", f"http://127.0.0.1:{args.port}"],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                encoding="utf-8", errors="replace", cwd=PROJECT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            log_path = runtime / f"mobile-demo-{os.getpid()}-tunnel.log"
            reader = threading.Thread(target=tunnel_output, args=(process, log_path, stopping), daemon=True)
            reader.start()
            print("正在生成手机分享链接；生成后会显示在这个终端。", flush=True)
        if not args.no_browser:
            timer = threading.Timer(0.3, webbrowser.open, args=(login,))
            timer.daemon = True
            timer.start()
        http.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stopping.set()
        server.PERSON_TYPE_RUNTIME.stop()
        if timer:
            timer.cancel()
        stop_tunnel(process)
        if reader:
            reader.join(timeout=2)
        if process and process.stdout:
            process.stdout.close()
        http.server_close()


if __name__ == "__main__":
    main()
