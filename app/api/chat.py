import uuid
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse
from app.core.auth import TokenPayload, require_auth
from app.core.config import settings
from app.core.database import get_db
from app.schemas.chat import (
    ChatRequest,
    ChatStreamRequest,
    ChatResponse,
    ConversationCreate,
    ConversationResponse,
    Usage,
)
from app.services.openclaw import openclaw_service
from app.services.db_service import (
    ConversationService,
    ChatRequestService,
    MessageService,
    UsageService,
    AuditService,
)


router = APIRouter(prefix="/api", dependencies=[Depends(require_auth)])


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, auth: TokenPayload = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    tenant_id = auth.tenant_id
    user_id = auth.user_id
    conversation_id = request.conversation_id
    message = request.message
    client_request_id = request.client_request_id

    existing = await ChatRequestService.find_existing_request(
        db, tenant_id, user_id, conversation_id, client_request_id
    )
    if existing and existing.status in ("received", "processing"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "REQUEST_IN_PROGRESS", "message": "相同 client_request_id 的请求仍在处理中"},
        )

    # Check if client_request_id was ever used in any conversation
    if await ChatRequestService.is_client_request_id_used(db, tenant_id, user_id, client_request_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "CLIENT_REQUEST_ID_USED", "message": "该 client_request_id 已被使用"},
        )

    conversation = await ConversationService.get_or_create_conversation(
        db, tenant_id, user_id, conversation_id
    )
    agent_id = conversation.agent_id
    prompt_version = conversation.prompt_version
    policy_version = conversation.policy_version

    chat_request = await ChatRequestService.create_request(
        db=db,
        tenant_id=tenant_id,
        user_id=user_id,
        conversation_id=conversation_id,
        client_request_id=client_request_id,
        agent_id=agent_id,
        prompt_version=prompt_version,
        policy_version=policy_version,
        stream=False,
    )
    request_id = chat_request.id

    user_message = await MessageService.create_user_message(
        db=db,
        tenant_id=tenant_id,
        user_id=user_id,
        conversation_id=conversation_id,
        request_id=request_id,
        content=message,
    )

    assistant_message = await MessageService.create_assistant_message(
        db=db,
        tenant_id=tenant_id,
        user_id=user_id,
        conversation_id=conversation_id,
        request_id=request_id,
        status="streaming",
    )
    message_id = assistant_message.id

    await ChatRequestService.mark_processing(db, tenant_id, request_id)
    await db.commit()

    accumulated_content = ""
    tool_call_count = 0
    tool_calls_list = []
    input_tokens = 0
    output_tokens = 0
    model = settings.openclaw_agent_id
    latency_ms = 0
    finish_reason = "stop"
    openclaw_session_id = None
    error_code = None
    error_message = None
    start_time = datetime.utcnow()

    try:
        async for event in openclaw_service.chat_stream(
            tenant_id=tenant_id,
            user_id=user_id,
            conversation_id=conversation_id,
            message=message,
            client_request_id=client_request_id,
            openclaw_session_id=conversation.openclaw_session_id,
        ):
            event_name = event.get("event", "")
            event_data = event.get("data", {})

            if event_name == "delta":
                content_piece = event_data.get("content", "")
                if content_piece:
                    accumulated_content = content_piece

            elif event_name == "tool_call":
                tool_call_count += 1
                tool_name = event_data.get("tool", "unknown")
                tool_input = event_data.get("input", {})
                call_id = event_data.get("call_id", uuid.uuid4().hex[:8])
                tool_calls_list.append({
                    "tool": tool_name,
                    "input": tool_input,
                    "call_id": call_id,
                })

            elif event_name == "tool_call_done":
                tool_output = event_data.get("output", "")
                call_id = event_data.get("call_id", "")
                for tc in tool_calls_list:
                    if tc.get("call_id") == call_id:
                        tc["output"] = tool_output

            elif event_name == "done":
                usage = event_data.get("usage", {})
                input_tokens = usage.get("input_tokens", 0)
                output_tokens = usage.get("output_tokens", 0)
                model = usage.get("model", model)
                latency_ms = usage.get("latency_ms", 0)
                finish_reason = event_data.get("finish_reason", "stop")
                openclaw_session_id = event_data.get("session_id") or openclaw_session_id
                if event_data.get("content"):
                    accumulated_content = event_data["content"]

            elif event_name == "error":
                error_code = event_data.get("code", "UPSTREAM_ERROR")
                error_message = event_data.get("message", "涓婃父閿欒")
                retryable = event_data.get("retryable", True)

                await MessageService.update_content(
                    db, tenant_id, message_id, accumulated_content,
                    status="failed", tool_calls=tool_calls_list,
                )
                await ChatRequestService.mark_failed(
                    db, tenant_id, request_id, error_code, retryable,
                )
                await db.commit()

                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail={"code": error_code, "message": error_message},
                )

        end_time = datetime.utcnow()
        latency_ms = int((end_time - start_time).total_seconds() * 1000)

        await MessageService.update_content(
            db, tenant_id, message_id, accumulated_content,
            status="completed",
            token_input=input_tokens,
            token_output=output_tokens,
            tool_calls=tool_calls_list,
        )
        await ChatRequestService.mark_completed(
            db, tenant_id, request_id, message_id, openclaw_session_id,
        )
        if openclaw_session_id:
            await ConversationService.update_session(db, tenant_id, conversation_id, openclaw_session_id)
        await ConversationService.update_last_message_at(db, tenant_id, conversation_id)
        await db.commit()

        cost = (input_tokens * 0.3 + output_tokens * 1.2) / 1000
        await UsageService.create_usage_log(
            db=db,
            tenant_id=tenant_id,
            user_id=user_id,
            conversation_id=conversation_id,
            request_id=request_id,
            agent_id=agent_id,
            prompt_version=prompt_version,
            policy_version=policy_version,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            tool_call_count=tool_call_count,
            tool_calls=tool_calls_list,
            latency_ms=latency_ms,
            cost=cost,
        )
        await AuditService.log(
            db=db,
            tenant_id=tenant_id,
            operator_user_id=user_id,
            event_type="chat_completed",
            conversation_id=conversation_id,
            request_id=request_id,
            payload={"message_id": message_id, "tool_call_count": tool_call_count},
        )
        await db.commit()

        return ChatResponse(
            id=message_id,
            conversation_id=conversation_id,
            content=accumulated_content,
            openclaw_session_id=openclaw_session_id,
            usage=Usage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                model=model,
                latency_ms=latency_ms,
            ),
        )

    except HTTPException:
        raise
    except Exception as e:
        await MessageService.update_content(
            db, tenant_id, message_id, accumulated_content, status="failed",
        )
        await ChatRequestService.mark_failed(
            db, tenant_id, request_id, "UPSTREAM_UNAVAILABLE", True,
        )
        await db.commit()

        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "UPSTREAM_UNAVAILABLE", "message": str(e)},
        )


async def event_generator(request: ChatStreamRequest, auth: TokenPayload, db: AsyncSession):
    tenant_id = auth.tenant_id
    user_id = auth.user_id
    conversation_id = request.conversation_id
    message = request.message
    client_request_id = request.client_request_id

    existing = await ChatRequestService.find_existing_request(
        db, tenant_id, user_id, conversation_id, client_request_id
    )
    if existing and existing.status in ("received", "processing"):
        error_id = f"msg_{uuid.uuid4().hex[:8]}"
        yield {
            "event": "error",
            "data": {
                "id": error_id,
                "code": "REQUEST_IN_PROGRESS",
                "message": "相同 client_request_id 的请求仍在处理中",
                "retryable": False,
            },
        }
        return

    # Check if client_request_id was ever used in any conversation
    if await ChatRequestService.is_client_request_id_used(db, tenant_id, user_id, client_request_id):
        yield {
            "event": "error",
            "data": {
                "id": f"msg_{uuid.uuid4().hex[:8]}",
                "code": "CLIENT_REQUEST_ID_USED",
                "message": "该 client_request_id 已被使用",
                "retryable": False,
            },
        }
        return

    # Validate conversation - check if deleted before creating/yielding any events
    try:
        conversation = await ConversationService.get_or_create_conversation(
            db, tenant_id, user_id, conversation_id
        )
    except HTTPException as e:
        yield {
            "event": "error",
            "data": {
                "id": f"msg_{uuid.uuid4().hex[:8]}",
                "code": e.detail.get("code", "CONVERSATION_ERROR"),
                "message": e.detail.get("message", "会话错误"),
                "retryable": False,
            },
        }
        return
    except Exception as e:
        yield {
            "event": "error",
            "data": {
                "id": f"msg_{uuid.uuid4().hex[:8]}",
                "code": "INTERNAL_ERROR",
                "message": str(e),
                "retryable": True,
            },
        }
        return

    agent_id = conversation.agent_id
    prompt_version = conversation.prompt_version
    policy_version = conversation.policy_version

    chat_request = await ChatRequestService.create_request(
        db=db,
        tenant_id=tenant_id,
        user_id=user_id,
        conversation_id=conversation_id,
        client_request_id=client_request_id,
        agent_id=agent_id,
        prompt_version=prompt_version,
        policy_version=policy_version,
        stream=True,
    )
    request_id = chat_request.id

    user_message = await MessageService.create_user_message(
        db=db,
        tenant_id=tenant_id,
        user_id=user_id,
        conversation_id=conversation_id,
        request_id=request_id,
        content=message,
    )

    assistant_message = await MessageService.create_assistant_message(
        db=db,
        tenant_id=tenant_id,
        user_id=user_id,
        conversation_id=conversation_id,
        request_id=request_id,
        status="streaming",
    )
    message_id = assistant_message.id
    created_at = datetime.utcnow().isoformat() + "Z"

    yield {
        "event": "start",
        "data": {
            "id": message_id,
            "conversation_id": conversation_id,
            "client_request_id": client_request_id,
            "created_at": created_at,
        },
    }

    await ChatRequestService.mark_processing(db, tenant_id, request_id)
    await db.commit()

    accumulated_content = ""
    tool_call_count = 0
    tool_calls_list = []
    input_tokens = 0
    output_tokens = 0
    model = settings.openclaw_agent_id
    latency_ms = 0
    finish_reason = "stop"
    openclaw_session_id = None
    start_time = datetime.utcnow()

    try:
        async for event in openclaw_service.chat_stream(
            tenant_id=tenant_id,
            user_id=user_id,
            conversation_id=conversation_id,
            message=message,
            client_request_id=client_request_id,
            openclaw_session_id=conversation.openclaw_session_id,
        ):
            event_name = event.get("event", "")
            event_data = event.get("data", {})

            if event_name == "delta":
                content_piece = event_data.get("content", "")
                if content_piece:
                    accumulated_content = content_piece
                    yield {"event": "delta", "data": {"content": accumulated_content}}

            elif event_name == "tool_call":
                tool_call_count += 1
                tool_name = event_data.get("tool", "unknown")
                tool_input = event_data.get("input", {})
                call_id = event_data.get("call_id", uuid.uuid4().hex[:8])
                tool_calls_list.append({
                    "tool": tool_name,
                    "input": tool_input,
                    "call_id": call_id,
                })
                yield {
                    "event": "tool_call",
                    "data": {
                        "tool": tool_name,
                        "input": tool_input,
                        "call_id": call_id,
                    },
                }

            elif event_name == "tool_call_done":
                tool_output = event_data.get("output", "")
                tool_name = event_data.get("tool", "unknown")
                call_id = event_data.get("call_id", "")
                for tc in tool_calls_list:
                    if tc.get("call_id") == call_id:
                        tc["output"] = tool_output
                yield {
                    "event": "tool_call_done",
                    "data": {
                        "tool": tool_name,
                        "output": tool_output,
                        "call_id": call_id,
                    },
                }

            elif event_name == "done":
                usage = event_data.get("usage", {})
                input_tokens = usage.get("input_tokens", 0)
                output_tokens = usage.get("output_tokens", 0)
                model = usage.get("model", model)
                latency_ms = usage.get("latency_ms", 0)
                finish_reason = event_data.get("finish_reason", "stop")
                openclaw_session_id = event_data.get("session_id") or openclaw_session_id
                if event_data.get("content"):
                    accumulated_content = event_data["content"]

            elif event_name == "error":
                error_code = event_data.get("code", "UPSTREAM_UNAVAILABLE")
                error_message = event_data.get("message", "上游错误")
                retryable = event_data.get("retryable", True)

                await MessageService.update_content(
                    db, tenant_id, message_id, accumulated_content,
                    status="failed", tool_calls=tool_calls_list,
                )
                await ChatRequestService.mark_failed(
                    db, tenant_id, request_id, error_code, retryable,
                )
                await db.commit()

                yield {
                    "event": "error",
                    "data": {
                        "id": message_id,
                        "code": error_code,
                        "message": error_message,
                        "retryable": retryable,
                    },
                }
                return

        end_time = datetime.utcnow()
        latency_ms = int((end_time - start_time).total_seconds() * 1000)

        await MessageService.update_content(
            db, tenant_id, message_id, accumulated_content,
            status="completed",
            token_input=input_tokens,
            token_output=output_tokens,
            tool_calls=tool_calls_list,
        )
        await ChatRequestService.mark_completed(
            db, tenant_id, request_id, message_id, openclaw_session_id,
        )
        if openclaw_session_id:
            await ConversationService.update_session(db, tenant_id, conversation_id, openclaw_session_id)
        await ConversationService.update_last_message_at(db, tenant_id, conversation_id)
        await db.commit()

        cost = (input_tokens * 0.3 + output_tokens * 1.2) / 1000
        await UsageService.create_usage_log(
            db=db,
            tenant_id=tenant_id,
            user_id=user_id,
            conversation_id=conversation_id,
            request_id=request_id,
            agent_id=agent_id,
            prompt_version=prompt_version,
            policy_version=policy_version,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            tool_call_count=tool_call_count,
            tool_calls=tool_calls_list,
            latency_ms=latency_ms,
            cost=cost,
        )
        await AuditService.log(
            db=db,
            tenant_id=tenant_id,
            operator_user_id=user_id,
            event_type="chat_completed",
            conversation_id=conversation_id,
            request_id=request_id,
            payload={"message_id": message_id, "tool_call_count": tool_call_count},
        )
        await db.commit()

        yield {
            "event": "done",
            "data": {
                "id": message_id,
                "content": accumulated_content,
                "usage": {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "model": model,
                    "latency_ms": latency_ms,
                },
                "finish_reason": finish_reason,
                "openclaw_session_id": openclaw_session_id,
            },
        }

    except Exception as e:
        await MessageService.update_content(
            db, tenant_id, message_id, accumulated_content, status="failed",
        )
        await ChatRequestService.mark_failed(
            db, tenant_id, request_id, "UPSTREAM_UNAVAILABLE", True,
        )
        await db.commit()

        yield {
            "event": "error",
            "data": {
                "id": message_id,
                "code": "UPSTREAM_UNAVAILABLE",
                "message": str(e),
                "retryable": True,
            },
        }


@router.post("/chat/stream")
async def chat_stream(
    request: ChatStreamRequest,
    auth: TokenPayload = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    async def generate():
        async for event in event_generator(request, auth, db):
            yield event

    return EventSourceResponse(generate())


@router.post("/conversations", response_model=ConversationResponse)
async def create_conversation(
    request: ConversationCreate,
    auth: TokenPayload = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    from app.models.models import Conversation

    conversation_id = f"conv_{uuid.uuid4().hex[:12]}"
    created_at = datetime.utcnow().isoformat() + "Z"

    conversation = Conversation(
        tenant_id=auth.tenant_id,
        id=conversation_id,
        user_id=auth.user_id,
        agent_id=request.agent_id,
        title=request.title,
        status="active",
        session_generation=0,
    )
    db.add(conversation)
    await db.commit()

    return ConversationResponse(
        conversation_id=conversation_id,
        agent_id=request.agent_id,
        title=request.title,
        status="active",
        created_at=created_at,
    )


@router.get("/conversations/{conversation_id}/messages")
async def get_messages(
    conversation_id: str,
    auth: TokenPayload = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import select
    from app.models.models import Message

    result = await db.execute(
        select(Message).where(
            Message.tenant_id == auth.tenant_id,
            Message.conversation_id == conversation_id,
            Message.user_id == auth.user_id,
        ).order_by(Message.created_at)
    )
    messages = result.scalars().all()

    return {
        "conversation_id": conversation_id,
        "items": [
            {
                "id": msg.id,
                "conversation_id": msg.conversation_id,
                "role": msg.role,
                "content": msg.content,
                "status": msg.status,
                "created_at": msg.created_at.isoformat() if msg.created_at else None,
            }
            for msg in messages
        ],
        "page": {"has_more": False, "next_before": None},
    }


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    auth: TokenPayload = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import update
    from app.models.models import Conversation

    await db.execute(
        update(Conversation)
        .where(
            Conversation.tenant_id == auth.tenant_id,
            Conversation.id == conversation_id,
            Conversation.user_id == auth.user_id,
        )
        .values(deleted_at=datetime.utcnow(), status="deleted")
    )
    await db.commit()

    return {"status": "deleted"}
