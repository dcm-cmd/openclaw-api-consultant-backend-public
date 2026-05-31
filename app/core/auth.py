from datetime import datetime, timedelta
from typing import Optional
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel


class TokenPayload(BaseModel):
    user_id: str
    tenant_id: str
    plan: str = "free"
    exp: Optional[datetime] = None


security = HTTPBearer()


def create_token(user_id: str, tenant_id: str, plan: str = "free", expires_delta: timedelta = timedelta(days=7)) -> str:
    from app.core.config import settings
    expire = datetime.utcnow() + expires_delta
    payload = {
        "user_id": user_id,
        "tenant_id": tenant_id,
        "plan": plan,
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def verify_token(credentials: HTTPAuthorizationCredentials) -> TokenPayload:
    from app.core.config import settings
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm]
        )
        return TokenPayload(**payload)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTH_INVALID", "message": "token 已过期"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTH_INVALID", "message": "token 无效"},
        )


def require_auth(credentials: HTTPAuthorizationCredentials = Depends(security)) -> TokenPayload:
    return verify_token(credentials)