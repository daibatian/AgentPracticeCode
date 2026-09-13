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
