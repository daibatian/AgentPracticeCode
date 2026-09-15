"""配额查询接口：让用户（以及以后的管理后台）能看到今日额度与已用量。"""
from fastapi import APIRouter, Depends, Request

from app.api.deps import get_current_user
from app.common.quota import quota_snapshot

router = APIRouter()


@router.get("/quota")
async def get_quota(request: Request, user: dict = Depends(get_current_user)):
    """当前用户今天的额度使用情况。

    quota = 0 表示不限量（remaining 为 null）；used 是输入 + 输出 token 之和。
    """
    return await quota_snapshot(request.app.state.pool, user["id"])
