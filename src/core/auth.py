"""Authentication helpers.

分两套鉴权（参考 flow2api）：
- 管理后台：账号密码登录，返回“管理会话 token”
- 对外使用接口：API Key（Authorization: Bearer <api_key>）
"""

from __future__ import annotations

import bcrypt
from typing import Optional

from fastapi import HTTPException, Security, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import config


security = HTTPBearer(auto_error=False)


class AuthManager:
    @staticmethod
    def verify_api_key(api_key: str) -> bool:
        return api_key == config.api_key

    @staticmethod
    def hash_password(password: str) -> str:
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    @staticmethod
    def verify_password(password: str, hashed: str) -> bool:
        try:
            return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
        except Exception:
            return False


async def verify_api_key_header(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security),
) -> str:
    api_key = credentials.credentials if credentials else None

    if not api_key:
        auth_hdr = request.headers.get("authorization") or ""
        if auth_hdr:
            api_key = auth_hdr.replace("Bearer ", "").replace("bearer ", "").strip()

    if not api_key:
        api_key = request.headers.get("x-api-key") or request.headers.get("api-key") or ""

    if api_key:
        if AuthManager.verify_api_key(api_key):
            return api_key
        raise HTTPException(status_code=401, detail="Invalid API key")

    # 本机回环 (127.0.0.1 / ::1 / localhost) 允许免 Auth 直通，避免 Codex/ccswitch 未发 Bearer 导致 403/502
    client_host = request.client.host if request.client else ""
    if client_host in ("127.0.0.1", "::1", "localhost", "testclient"):
        return config.api_key or "local"

    raise HTTPException(status_code=401, detail="API key is required")

