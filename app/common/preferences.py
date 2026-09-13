"""把用户的菜品偏好整理成给模型看的说明文本。"""
from __future__ import annotations

# 口味 / 辣度 / 饮食目标的可选值（空字符串 = 未设置）
TASTE_OPTIONS = ["", "清淡", "适中", "重口"]
SPICY_OPTIONS = ["", "不辣", "微辣", "中辣", "特辣"]
DIET_OPTIONS = ["", "不限", "减脂", "增肌", "控糖", "养胃"]

CUISINE_OPTIONS = [
    "家常菜",
    "川菜",
    "粤菜",
    "江浙菜",
    "西北菜",
    "西餐",
    "日料",
    "韩餐",
    "东南亚",
    "素食",
    "汤羹",
    "面食",
    "烘焙",
]

# 给模型补充"这个选项意味着什么"，避免它理解偏
_TASTE_HINT = {
    "清淡": "少油少盐、少放酱油和糖，突出食材本味",
    "适中": "正常家常口味",
    "重口": "味道浓郁，可以多用酱料、香料",
}
_DIET_HINT = {
    "减脂": "控制总热量，优先高蛋白低脂、多蔬菜",
    "增肌": "提高蛋白质比例，搭配优质碳水",
    "控糖": "少糖、少精制碳水，优先低升糖食材",
    "养胃": "温和少刺激，避免过辣过油过凉",
}


def _split(value: str | None) -> list[str]:
    if not value:
        return []
    # 中英文逗号、顿号都当分隔符
    parts: list[str] = []
    for chunk in value.replace("，", ",").replace("、", ",").split(","):
        item = chunk.strip()
        if item:
            parts.append(item)
    return parts


def format_user_context(row: dict | None) -> str:
    """把数据库里的「称呼 + 菜品偏好」拼成给模型看的说明。

    什么都没设置时返回空字符串——这样模型的行为和加这些功能之前完全一致。
    """
    if not row:
        return ""

    blocks: list[str] = []

    # 1) 称呼：让模型知道你叫什么
    nickname = (row.get("display_name") or "").strip()
    if nickname:
        blocks.append(
            "\n\n【称呼】\n"
            f"用户希望你称呼他为「{nickname}」。可以在开场或给出关键结论时自然地用一次，"
            "不要每句话都带上。"
        )

    # 2) 菜品偏好
    lines: list[str] = []

    taste = (row.get("taste") or "").strip()
    if taste:
        hint = _TASTE_HINT.get(taste)
        lines.append(f"- 口味：{taste}" + (f"（{hint}）" if hint else ""))

    spicy = (row.get("spicy_level") or "").strip()
    if spicy:
        lines.append(f"- 辣度：{spicy}")

    diet = (row.get("diet_goal") or "").strip()
    if diet and diet != "不限":
        hint = _DIET_HINT.get(diet)
        lines.append(f"- 饮食目标：{diet}" + (f"（{hint}）" if hint else ""))

    avoid = _split(row.get("avoid_ingredients"))
    if avoid:
        lines.append(f"- 忌口/过敏（绝对不能出现）：{'、'.join(avoid)}")

    cuisines = _split(row.get("preferred_cuisines"))
    if cuisines:
        lines.append(f"- 偏好菜系：{'、'.join(cuisines)}")

    notes = (row.get("notes") or "").strip()
    if notes:
        lines.append(f"- 其他要求：{notes}")

    if lines:
        blocks.append(
            "\n\n【当前用户的用餐偏好 —— 必须遵守】\n"
            + "\n".join(lines)
            + "\n\n请在检索和推荐菜谱时严格遵守以上偏好："
            "若检索到的菜谱与偏好冲突，请改选更符合的；"
            "用户当次对话里明确提出的要求优先级最高。"
        )

    return "".join(blocks)
