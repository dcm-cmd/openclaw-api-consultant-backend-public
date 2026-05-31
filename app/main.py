from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from app.api.chat import router as chat_router
from app.core.auth import create_token


app = FastAPI(
    title="OpenClaw API Consultant Backend",
    version="1.0.0",
    swagger_ui_init_oauth={"usePkceWithAuthorizationCodeGrant": True, "clientId": "openclaw-api-consultant"},
)

app.include_router(chat_router)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/auth/token")
async def get_token(user_id: str = "user-demo", tenant_id: str = "tenant-demo", plan: str = "free"):
    """生成测试 JWT Token。默认生成 user-demo/tenant-demo 的 7 天有效 token。
    生成后在 Swagger UI 右上角 Authorize 中输入 `Bearer <token>` 即可测试。
    """
    token = create_token(user_id=user_id, tenant_id=tenant_id, plan=plan)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user_id": user_id,
        "tenant_id": tenant_id,
        "plan": plan,
        "usage": f"Bearer {token}",
    }


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "服务器内部错误",
            }
        },
    )