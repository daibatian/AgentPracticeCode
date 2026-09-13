"""用户资料与菜品偏好。"""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.deps import get_current_user
from app.common.preferences import (
    CUISINE_OPTIONS,
    DIET_OPTIONS,
    SPICY_OPTIONS,
    TASTE_OPTIONS,
)
from app.common.security import hash_password, verify_password
from app.models.schemas import PasswordChange, ProfileUpdate

router = APIRouter()

PROFILE_FIELDS = (
    "display_name",
    "avatar",
    "phone",
    "signature",
    "taste",
    "spicy_level",
    "diet_goal",
    "avoid_ingredients",
    "preferred_cuisines",
    "notes",
)

# 头像存成 data URL（浏览器端压缩到 128x128 再传），限制一下大小
AVATAR_MAX_LEN = 400_000
PHONE_RE = re.compile(r"^1[3-9]\d{9}$")


def _row_to_profile(row: dict) -> dict:
    cuisines = row.get("preferred_cuisines") or ""
    return {
        "username": row.get("username") or "",
        "display_name": row.get("display_name") or "",
        "avatar": row.get("avatar") or "",
        "phone": row.get("phone") or "",
        "signature": row.get("signature") or "",
        "taste": row.get("taste") or "",
        "spicy_level": row.get("spicy_level") or "",
        "diet_goal": row.get("diet_goal") or "",
        "avoid_ingredients": row.get("avoid_ingredients") or "",
        "preferred_cuisines": [c for c in cuisines.split(",") if c],
        "notes": row.get("notes") or "",
    }


async def _fetch_profile(pool, user_id: int) -> dict | None:
    async with pool.connection() as conn:
        cur = await conn.execute(
            "select username, " + ", ".join(PROFILE_FIELDS) +
            " from app_users where id = %s",
            (user_id,),
        )
        return await cur.fetchone()


@router.get("/profile")
async def get_profile(request: Request, user: dict = Depends(get_current_user)):
    """读取当前用户的资料和菜品偏好。"""
    row = await _fetch_profile(request.app.state.pool, user["id"])
    if row is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    return _row_to_profile(row)


@router.put("/profile")
async def update_profile(
    payload: ProfileUpdate,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """更新资料/偏好；只更新请求里出现的字段。"""
    data = payload.model_dump(exclude_unset=True)
    updates: dict[str, str] = {}

    if "display_name" in data:
        updates["display_name"] = (data["display_name"] or "").strip()[:20]

    if "avatar" in data:
        avatar = (data["avatar"] or "").strip()
        if avatar and not avatar.startswith("data:image/"):
            raise HTTPException(status_code=400, detail="头像格式不正确")
        if len(avatar) > AVATAR_MAX_LEN:
            raise HTTPException(status_code=400, detail="头像图片太大，请换一张")
        updates["avatar"] = avatar

    if "phone" in data:
        phone = (data["phone"] or "").strip()
        if phone and not PHONE_RE.match(phone):
            raise HTTPException(status_code=400, detail="手机号格式不正确（11 位）")
        updates["phone"] = phone

    if "signature" in data:
        updates["signature"] = (data["signature"] or "").strip()[:60]

    if "taste" in data:
        value = (data["taste"] or "").strip()
        if value not in TASTE_OPTIONS:
            raise HTTPException(status_code=400, detail="口味取值不合法")
        updates["taste"] = value

    if "spicy_level" in data:
        value = (data["spicy_level"] or "").strip()
        if value not in SPICY_OPTIONS:
            raise HTTPException(status_code=400, detail="辣度取值不合法")
        updates["spicy_level"] = value

    if "diet_goal" in data:
        value = (data["diet_goal"] or "").strip()
        if value not in DIET_OPTIONS:
            raise HTTPException(status_code=400, detail="饮食目标取值不合法")
        updates["diet_goal"] = value

    if "avoid_ingredients" in data:
        updates["avoid_ingredients"] = (data["avoid_ingredients"] or "").strip()[:200]

    if "preferred_cuisines" in data:
        raw = data["preferred_cuisines"] or []
        invalid = [c for c in raw if c not in CUISINE_OPTIONS]
        if invalid:
            raise HTTPException(
                status_code=400, detail=f"不支持的菜系：{'、'.join(invalid)}"
            )
        # 去重后存成逗号分隔字符串
        seen: list[str] = []
        for c in raw:
            if c not in seen:
                seen.append(c)
        updates["preferred_cuisines"] = ",".join(seen)

    if "notes" in data:
        updates["notes"] = (data["notes"] or "").strip()[:300]

    pool = request.app.state.pool
    if updates:
        # 列名来自上面的白名单，值是参数化传入的
        assignments = ", ".join(f"{col} = %s" for col in updates)
        async with pool.connection() as conn:
            await conn.execute(
                f"update app_users set {assignments} where id = %s",
                (*updates.values(), user["id"]),
            )

    row = await _fetch_profile(pool, user["id"])
    return _row_to_profile(row or {})


@router.post("/profile/password")
async def change_password(
    payload: PasswordChange,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """修改密码：校验旧密码 → 存新哈希 → 其它设备的登录失效。"""
    new_password = payload.new_password or ""
    if len(new_password) < 6:
        raise HTTPException(status_code=400, detail="新密码至少 6 位")
    if new_password == (payload.old_password or ""):
        raise HTTPException(status_code=400, detail="新密码不能和旧密码相同")

    pool = request.app.state.pool
    async with pool.connection() as conn:
        cur = await conn.execute(
            "select password_hash from app_users where id = %s", (user["id"],)
        )
        row = await cur.fetchone()

    if row is None or not verify_password(
        payload.old_password or "", row["password_hash"]
    ):
        raise HTTPException(status_code=400, detail="原密码不正确")

    async with pool.connection() as conn:
        await conn.execute(
            "update app_users set password_hash = %s where id = %s",
            (hash_password(new_password), user["id"]),
        )
        # 除了当前这台设备，其它登录令牌全部作废
        await conn.execute(
            "delete from app_sessions where user_id = %s and token <> %s",
            (user["id"], user["token"]),
        )

    return {"ok": True, "message": "密码已更新，其它设备需要重新登录"}
