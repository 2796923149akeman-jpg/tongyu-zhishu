"""Local-only account setup; passwords are entered without echo and never logged."""
import argparse
import getpass
import os
from pathlib import Path

from access_control import AccessStore


def account_store():
    path = Path(os.environ.get("DASHBOARD_AUTH_FILE", str(Path(__file__).parent / "auth_config.json")))
    return AccessStore(path)


def prompt_admin(store, username=None):
    username = username or input("管理员用户名：")
    password = getpass.getpass("管理员密码（至少 6 位，不显示）：")
    if password != getpass.getpass("再次输入密码："):
        raise ValueError("两次密码不一致，未保存。")
    store.create_user(username, password, role="admin")
    print("管理员已创建，后续启动会自动沿用此账号。")


def ensure_admin():
    store = account_store()
    if not store.initialized:
        print("首次启动，请创建管理员账号；以后启动无需重复设置。")
        prompt_admin(store)


def main():
    parser = argparse.ArgumentParser(description="创建独立的电脑管理员账号（不会公开服务）")
    parser.add_argument("--username", help="管理员登录名；省略则交互输入")
    args = parser.parse_args()
    try:
        prompt_admin(account_store(), args.username)
    except ValueError as exc:
        parser.exit(1, str(exc) + "\n")
    print("若网页服务正在运行，请重启后登录。")


if __name__ == "__main__":
    main()
