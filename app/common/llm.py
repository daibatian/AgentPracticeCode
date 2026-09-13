"""模型配置与「该不该降级」的判断。"""
from __future__ import annotations

import os

# 主模型（可用环境变量覆盖，换模型不需要改代码）
DEFAULT_MODEL = "qwen3.8-flash"

# 备用模型：主模型不可用时按顺序往下试
DEFAULT_FALLBACKS = [
    "qwen3.7-plus",
    "qwen3.7-flash",
    "qwen3.7-max",
    "qwen3.6-plus",
    "qwen3.6-flash",
    "qwen3.5-flash",
    "qwen3.5-plus",
]

# 这些 HTTP 状态码说明"不是我们请求写错了"，可以换模型重试
FALLBACK_STATUS_CODES = {402, 408, 409, 425, 429, 500, 502, 503, 504}

# 报错文本里出现这些词，说明额度/限流/模型不可用，同样换模型
FALLBACK_KEYWORDS = (
    "quota",
    "insufficient",
    "balance",
    "rate limit",
    "rate_limit",
    "too many requests",
    "overloaded",
    "capacity",
    "model not exist",
    "model_not_found",
    "does not exist",
    "invalid model",
    "not supported",
    "unavailable",
    "额度",
    "欠费",
    "余额不足",
    "限流",
    "模型不存在",
)


def _split_models(value: str | None) -> list[str]:
    if not value:
        return []
    return [
        item.strip()
        for item in value.replace("，", ",").split(",")
        if item.strip()
    ]


def model_names() -> list[str]:
    """主模型 + 备用模型（去重、保持顺序）。"""
    primary = (os.getenv("MODEL_NAME") or DEFAULT_MODEL).strip()
    fallbacks = _split_models(os.getenv("MODEL_FALLBACKS")) or DEFAULT_FALLBACKS

    names: list[str] = []
    for name in [primary, *fallbacks]:
        if name and name not in names:
            names.append(name)
    return names


def should_fallback(exc: BaseException) -> bool:
    """判断这个异常是否值得换个模型再试。

    额度耗尽、限流、服务端 5xx、模型不存在/不可用 → 值得换；
    请求本身有问题（消息格式错等）→ 不值得，换个模型也一样失败。
    """
    seen: set[int] = set()
    current: BaseException | None = exc

    while current is not None and id(current) not in seen:
        seen.add(id(current))

        for attr in ("status_code", "http_status", "code"):
            value = getattr(current, attr, None)
            if isinstance(value, int) and value in FALLBACK_STATUS_CODES:
                return True

        text = str(current).lower()
        if any(keyword in text for keyword in FALLBACK_KEYWORDS):
            return True

        current = current.__cause__ or current.__context__

    return False
