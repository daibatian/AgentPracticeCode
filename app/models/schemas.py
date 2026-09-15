from typing import Optional, List

from pydantic import BaseModel

# --- 2. 数据模型 ---
class ChatRequest(BaseModel):
    message: str
    image_url: Optional[str] = None
    thread_id: str


class RegisterRequest(BaseModel):
    username: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class AuthResponse(BaseModel):
    token: str
    username: str


class ProfileUpdate(BaseModel):
    """用户资料 / 菜品偏好；字段全部可选，只更新传上来的。"""

    # 基础信息
    display_name: Optional[str] = None
    avatar: Optional[str] = None
    phone: Optional[str] = None
    signature: Optional[str] = None
    # 口味偏好
    taste: Optional[str] = None
    spicy_level: Optional[str] = None
    diet_goal: Optional[str] = None
    avoid_ingredients: Optional[str] = None
    preferred_cuisines: Optional[List[str]] = None
    notes: Optional[str] = None


class PasswordChange(BaseModel):
    old_password: str
    new_password: str


class AdminUserUpdate(BaseModel):
    """管理端修改用户：权限与额度覆盖，两个字段都可以不传。

    不传 = 不改；`weekly_token_quota` 传 null = 清掉覆盖、恢复用全局默认额度。
    """

    is_admin: Optional[bool] = None
    weekly_token_quota: Optional[int] = None
