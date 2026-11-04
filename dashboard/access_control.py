"""Small, local account store for the teaching demo; no third-party dependencies."""
from __future__ import annotations

import copy
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import tempfile
import threading
import time
import unicodedata

MODULES = ("monitor", "events", "chat", "health", "reports")
DEFAULT_POLICY = {"modules": dict.fromkeys(MODULES, True), "video": False, "dialogue_raw": False}
COOKIE_NAME = "tongyu_session"


def validate_policy(value):
    if (not isinstance(value, dict) or set(value) != set(DEFAULT_POLICY)
            or not isinstance(value.get("modules"), dict) or set(value["modules"]) != set(MODULES)):
        raise ValueError("展示设置格式不正确")
    if any(type(v) is not bool for v in [*value["modules"].values(), value["video"], value["dialogue_raw"]]):
        raise ValueError("展示开关必须为开启或关闭")
    return copy.deepcopy(value)


def credentials(username, password):
    if not isinstance(username, str) or not isinstance(password, str):
        raise ValueError("请输入用户名和密码")
    username = unicodedata.normalize("NFKC", username).strip()
    if not re.fullmatch(r"[\w.-]{3,32}", username):
        raise ValueError("用户名为 3–32 位汉字、字母、数字、下划线、点或短横线")
    if not 6 <= len(password) <= 128:
        raise ValueError("密码长度为 6–128 位")
    return username, password


def password_hash(password, salt):
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=16384, r=8, p=1, dklen=32).hex()


def student_ids(value):
    if value is None:
        return []
    if not isinstance(value, (list, tuple)):
        raise ValueError("绑定的学生必须是列表")
    normalized = []
    for student_id in value:
        if not isinstance(student_id, str) or not re.fullmatch(r"[A-Za-z0-9-]{3,20}", student_id.strip()):
            raise ValueError("学生编号格式不正确")
        if student_id.strip() not in normalized:
            normalized.append(student_id.strip())
    if not 1 <= len(normalized) <= 20:
        raise ValueError("家长账号必须绑定 1–20 名学生")
    return normalized


class AccessStore:
    idle_seconds = 30 * 60
    lifetime_seconds = 8 * 60 * 60
    anonymous_seconds = 15 * 60
    rate_seconds = 10 * 60

    def __init__(self, path, *, secure=True, clock=time.time):
        self.path = Path(path)
        self.secure = secure
        self.clock = clock
        self.lock = threading.RLock()
        self.sessions = {}
        self.attempts = {}
        self.users = {}
        self.policy = copy.deepcopy(DEFAULT_POLICY)
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.users = data["users"]
            self.policy = validate_policy(data["policy"])
            if not isinstance(self.users, dict):
                raise ValueError("Invalid local account store")

    def _save(self, users, policy):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=".auth_config-", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump({"users": users, "policy": policy}, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.path)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    @property
    def initialized(self):
        with self.lock:
            return any(u["role"] == "admin" for u in self.users.values())

    def create_user(self, username, password, *, role="viewer", bound_student_ids=None):
        username, password = credentials(username, password)
        if role not in ("viewer", "admin", "parent"):
            raise ValueError("Invalid role")
        bound_student_ids = student_ids(bound_student_ids) if role == "parent" else []
        with self.lock:
            if username.casefold() in self.users:
                raise ValueError("该用户名不可用，请换一个")
            if len(self.users) >= 200:
                raise ValueError("演示账号数量已达上限，请联系管理员")
            salt = secrets.token_bytes(16)
            users = copy.deepcopy(self.users)
            users[username.casefold()] = {"username": username, "role": role,
                                         "salt": salt.hex(), "password_hash": password_hash(password, salt),
                                         "student_ids": bound_student_ids}
            self._save(users, self.policy)
            self.users = users

    def set_policy(self, policy):
        value = validate_policy(policy)
        with self.lock:
            self._save(self.users, value)
            self.policy = value
        return copy.deepcopy(value)

    def get_policy(self):
        with self.lock:
            return copy.deepcopy(self.policy)

    def public_user(self, session):
        if not session:
            return None
        with self.lock:
            user = self.users.get(session.get("username"))
            if not user:
                return None
            result = {k: user[k] for k in ("username", "role")}
            if user["role"] == "parent":
                result["student_ids"] = list(user.get("student_ids", []))
            return result

    def permitted(self, session, key):
        user = self.public_user(session)
        if not user:
            return False
        if user["role"] == "admin":
            return True
        if user["role"] == "parent":
            return False
        with self.lock:
            return bool(self.policy["modules"].get(key, self.policy.get(key, False)))

    def list_parents(self):
        with self.lock:
            return sorted(
                [
                    {
                        "username": user["username"],
                        "student_ids": list(user.get("student_ids", [])),
                    }
                    for user in self.users.values()
                    if user.get("role") == "parent"
                ],
                key=lambda item: item["username"].casefold(),
            )

    def update_parent_bindings(self, username, bound):
        normalized = student_ids(bound)
        with self.lock:
            key = username.strip().casefold()
            user = self.users.get(key)
            if not user or user.get("role") != "parent":
                raise ValueError("家长账号不存在")
            users = copy.deepcopy(self.users)
            users[key]["student_ids"] = normalized
            self._save(users, self.policy)
            self.users = users
            return {"username": users[key]["username"], "student_ids": normalized}

    def rate_limited(self, key, limit, *, record=False):
        with self.lock:
            now = self.clock()
            self.attempts = {k: [t for t in v if now - t < self.rate_seconds]
                             for k, v in self.attempts.items() if v and now - v[-1] < self.rate_seconds}
            times = self.attempts.get(key, [])
            blocked = len(times) >= limit
            if record and not blocked:
                # A global cap also bounds attacker-controlled username keys.
                if len(self.attempts) >= 4096 and key not in self.attempts:
                    return True
                self.attempts[key] = times + [now]
            return blocked

    def authenticate(self, username, password, peer):
        username, password = credentials(username, password)
        key = "login:" + username.casefold()
        source = "source:" + peer
        if self.rate_limited(key, 5) or self.rate_limited(source, 60):
            return "limited", None
        with self.lock:
            user = self.users.get(username.casefold())
            salt = bytes.fromhex(user["salt"]) if user else bytes(16)
            digest = password_hash(password, salt)
            valid = user and hmac.compare_digest(user["password_hash"], digest)
            if not valid:
                self.rate_limited(key, 5, record=True)
                self.rate_limited(source, 60, record=True)
                return "invalid", None
            self.attempts.pop(key, None)
            return "ok", username.casefold()

    def _expired(self, session, now):
        life = self.lifetime_seconds if session["username"] else self.anonymous_seconds
        return now - session["created"] >= life or now - session["last"] >= self.idle_seconds

    def new_session(self, username=None):
        with self.lock:
            now = self.clock()
            self.sessions = {k: v for k, v in self.sessions.items() if not self._expired(v, now)}
            if len(self.sessions) >= 2048:
                oldest = min(self.sessions, key=lambda k: self.sessions[k]["last"])
                self.sessions.pop(oldest)
            token = secrets.token_urlsafe(32)
            session = {"username": username, "created": now, "last": now, "csrf": secrets.token_urlsafe(32)}
            self.sessions[hashlib.sha256(token.encode()).hexdigest()] = session
            return token, session.copy()

    def session(self, token, *, touch=True):
        if not token or len(token) > 128:
            return None
        with self.lock:
            key = hashlib.sha256(token.encode()).hexdigest()
            value = self.sessions.get(key)
            now = self.clock()
            if not value:
                return None
            if self._expired(value, now):
                self.sessions.pop(key, None)
                return None
            if touch:
                value["last"] = now
            return value.copy()

    def revoke(self, token):
        with self.lock:
            self.sessions.pop(hashlib.sha256(token.encode()).hexdigest(), None)

    def cookie(self, token, *, clear=False):
        age = 0 if clear else self.lifetime_seconds
        return (f"{COOKIE_NAME}={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age={age}"
                + ("; Secure" if self.secure else ""))
