import os
import uuid
from datetime import timedelta

import alibabacloud_oss_v2 as oss
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user

# 加载环境变量

load_dotenv()
router = APIRouter()

# 从环境变量中加载凭证信息，用于身份验证
credentials_provider = oss.credentials.EnvironmentVariableCredentialsProvider()

# 加载SDK的默认配置，并设置凭证提供者
cfg = oss.config.load_default()
cfg.credentials_provider = credentials_provider

# 方式一：只填写Region（推荐）
# 必须指定Region ID，SDK会根据Region自动构造HTTPS访问域名
cfg.region = 'cn-beijing'

# 使用配置好的信息创建OSS客户端
client = oss.Client(cfg)

# OSS 域名配置
OSS_ENDPOINT = os.getenv("OSS_ENDPOINT", "oss-cn-beijing.aliyuncs.com")
OSS_BUCKET = os.getenv("OSS_BUCKET")

# 只允许上传这几类图片，别的扩展名一律拒绝
IMAGE_CONTENT_TYPES = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "gif": "image/gif",
    "webp": "image/webp",
}


def _extension_of(filename: str) -> str:
    """取扩展名并校验；不是图片类型就直接 400。"""
    name = (filename or "").strip().lower()
    ext = name.rsplit(".", 1)[-1] if "." in name else ""
    if ext not in IMAGE_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail="只支持 jpg / jpeg / png / gif / webp 图片",
        )
    return ext


@router.get("/oss/presign")
def presign_upload(filename: str, user: dict = Depends(get_current_user)):
    """签发一个只能上传图片的预签名 PUT 地址。

    对象名（key）由服务端生成，规则是 `u<用户id>/<随机名>.<扩展名>`：
    - 客户端传的 filename 只用来判断图片类型，不再直接当 key 用，
      所以没人能覆盖别人上传的图片，也没法往桶里写任意名字的文件；
    - 按用户分目录，以后后台要清理某个用户的图片，按前缀删就行。
    """
    if not OSS_BUCKET:
        raise HTTPException(status_code=500, detail="服务端未配置 OSS_BUCKET")

    ext = _extension_of(filename)
    content_type = IMAGE_CONTENT_TYPES[ext]
    key = f"u{user['id']}/{uuid.uuid4().hex}.{ext}"

    pre_result = client.presign(oss.PutObjectRequest(
        bucket=OSS_BUCKET,
        key=key,
        content_type=content_type,
    ), expires=timedelta(seconds=3600))

    # 返回上传 URL 和可访问的图片路径
    return {
        "uploadUrl": pre_result.url.strip('"'),
        "contentType": content_type,
        "accessUrl": f"https://{OSS_BUCKET}.{OSS_ENDPOINT}/{key}"
    }
