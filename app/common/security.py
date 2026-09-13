"""密码哈希与登录令牌（只用标准库，不引入额外依赖）。"""
from __future__ import annotations

import hashlib
import hmac
import secrets

# PBKDF2 的迭代次数：越大越安全、越慢，20 万次在现代机器上约 0.1 秒
_ITERATIONS = 200_000
_ALGO = "pbkdf2_sha256"


def hash_password(password: str) -> str:
    """把明文密码变成不可逆的哈希串，格式：算法$迭代次数$盐$哈希。"""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITERATIONS)
    return f"{_ALGO}${_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """校验明文密码是否匹配数据库里的哈希。"""
    try:
        algo, iterations, salt_hex, digest_hex = stored.split("$")
        if algo != _ALGO:
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt_hex), int(iterations)
        )
    except (ValueError, AttributeError):
        return False
    # 用 compare_digest 做常数时间比较，避免时序攻击
    return hmac.compare_digest(digest.hex(), digest_hex)


def new_token() -> str:
    """生成一个新的登录令牌（随机、不可预测）。"""
    return secrets.token_urlsafe(32)
