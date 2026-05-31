import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.models import (
    Conversation,
    ChatRequest,
    Message,
    UsageLog,
    AuditLog,
    generate_id,
)


class ConversationService:
    @staticmethod
    async def get_or_create_conversation(
        db: AsyncSession,
        tenant_id: str,
        user_id: str,
        conversation_id: str,
        agent_id: str = "consultant-main",
    ):
        from fastapi import HTTPException

        # Check if conversation exists (including deleted ones)
        result = await db.execute(
            select(Conversation).where(
                Conversation.tenant_id == tenant_id,
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
            )
        )
        existing = result.scalar_one_or_none()

        if existing and existing.deleted_at is not None:
            # Conversation was soft-deleted, do not allow reuse
            raise HTTPException(
                status_code=410,  # Gone
                detail={"code": "CONVERSATION_DELETED", "message": "该会话已被删除，不可复用"},
            )

        # Check for active conversation
        result = await db.execute(
            select(Conversation).where(
                Conversation.tenant_id == tenant_id,
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
                Conversation.deleted_at.is_(None),
            )
        )
        conversation = result.scalar_one_or_none()

        if not conversation:
            conversation = Conversation(
                tenant_id=tenant_id,
                id=conversation_id,
                user_id=user_id,
                agent_id=agent_id,
                title="新的咨询",
                status="active",
                session_generation=0,
            )
            db.add(conversation)
            await db.flush()

        return conversation

    @staticmethod
    async def update_session(
        db: AsyncSession,
        tenant_id: str,
        conversation_id: str,
        openclaw_session_id: str,
    ):
        await db.execute(
            update(Conversation)
            .where(
                Conversation.tenant_id == tenant_id,
                Conversation.id == conversation_id,
            )
            .values(
                openclaw_session_id=openclaw_session_id,
                session_generation=Conversation.session_generation + 1,
            )
        )

    @staticmethod
    async def update_last_message_at(
        db: AsyncSession,
        tenant_id: str,
        conversation_id: str,
    ):
        await db.execute(
            update(Conversation)
            .where(
                Conversation.tenant_id == tenant_id,
                Conversation.id == conversation_id,
            )
            .values(last_message_at=datetime.utcnow())
        )


class ChatRequestService:
    @staticmethod
    async def find_existing_request(
        db: AsyncSession,
        tenant_id: str,
        user_id: str,
        conversation_id: str,
        client_request_id: str,
    ) -> Optional[ChatRequest]:
        # Check for active requests with same client_request_id in ANY conversation
        result = await db.execute(
            select(ChatRequest).where(
                ChatRequest.tenant_id == tenant_id,
                ChatRequest.user_id == user_id,
                ChatRequest.client_request_id == client_request_id,
                ChatRequest.status.in_(["received", "processing"]),
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def is_client_request_id_used(
        db: AsyncSession,
        tenant_id: str,
        user_id: str,
        client_request_id: str,
    ) -> bool:
        # Check if client_request_id was ever used (in any conversation, any status)
        # This prevents reuse of client_request_id even if the previous request completed
        result = await db.execute(
            select(ChatRequest).where(
                ChatRequest.tenant_id == tenant_id,
                ChatRequest.user_id == user_id,
                ChatRequest.client_request_id == client_request_id,
            )
        )
        return result.scalar_one_or_none() is not None

    @staticmethod
    async def create_request(
        db: AsyncSession,
        tenant_id: str,
        user_id: str,
        conversation_id: str,
        client_request_id: str,
        agent_id: str,
        prompt_version: str,
        policy_version: str,
        stream: bool = False,
    ) -> ChatRequest:
        request_id = generate_id("req")
        chat_request = ChatRequest(
            tenant_id=tenant_id,
            id=request_id,
            conversation_id=conversation_id,
            user_id=user_id,
            client_request_id=client_request_id,
            status="received",
            agent_id=agent_id,
            prompt_version=prompt_version,
            policy_version=policy_version,
            stream=stream,
            retry_count=0,
        )
        db.add(chat_request)
        await db.flush()
        return chat_request

    @staticmethod
    async def mark_processing(
        db: AsyncSession,
        tenant_id: str,
        request_id: str,
    ):
        await db.execute(
            update(ChatRequest)
            .where(
                ChatRequest.tenant_id == tenant_id,
                ChatRequest.id == request_id,
            )
            .values(
                status="processing",
                started_at=datetime.utcnow(),
            )
        )

    @staticmethod
    async def mark_completed(
        db: AsyncSession,
        tenant_id: str,
        request_id: str,
        response_message_id: str,
        openclaw_session_id: Optional[str] = None,
    ):
        await db.execute(
            update(ChatRequest)
            .where(
                ChatRequest.tenant_id == tenant_id,
                ChatRequest.id == request_id,
            )
            .values(
                status="completed",
                response_message_id=response_message_id,
                openclaw_session_id=openclaw_session_id,
                finished_at=datetime.utcnow(),
            )
        )

    @staticmethod
    async def mark_failed(
        db: AsyncSession,
        tenant_id: str,
        request_id: str,
        error_code: str,
        retryable: bool = False,
    ):
        chat_req = await db.execute(
            select(ChatRequest).where(
                ChatRequest.tenant_id == tenant_id,
                ChatRequest.id == request_id,
            )
        )
        req = chat_req.scalar_one_or_none()
        if not req:
            return

        new_status = "failed"
        if retryable:
            new_status = "received"

        await db.execute(
            update(ChatRequest)
            .where(
                ChatRequest.tenant_id == tenant_id,
                ChatRequest.id == request_id,
            )
            .values(
                status=new_status,
                error_code=error_code,
                retry_count=req.retry_count + 1,
                finished_at=datetime.utcnow(),
            )
        )


class MessageService:
    @staticmethod
    async def create_user_message(
        db: AsyncSession,
        tenant_id: str,
        user_id: str,
        conversation_id: str,
        request_id: str,
        content: str,
    ) -> Message:
        message_id = generate_id("msg")
        message = Message(
            tenant_id=tenant_id,
            id=message_id,
            conversation_id=conversation_id,
            user_id=user_id,
            request_id=request_id,
            role="user",
            status="completed",
            content=content,
        )
        db.add(message)
        await db.flush()
        return message

    @staticmethod
    async def create_assistant_message(
        db: AsyncSession,
        tenant_id: str,
        user_id: str,
        conversation_id: str,
        request_id: str,
        content: str = "",
        status: str = "completed",
    ) -> Message:
        message_id = generate_id("msg")
        message = Message(
            tenant_id=tenant_id,
            id=message_id,
            conversation_id=conversation_id,
            user_id=user_id,
            request_id=request_id,
            role="assistant",
            status=status,
            content=content,
        )
        db.add(message)
        await db.flush()
        return message

    @staticmethod
    async def update_content(
        db: AsyncSession,
        tenant_id: str,
        message_id: str,
        content: str,
        status: str = "completed",
        token_input: int = 0,
        token_output: int = 0,
        tool_calls: list = None,
    ):
        await db.execute(
            update(Message)
            .where(
                Message.tenant_id == tenant_id,
                Message.id == message_id,
            )
            .values(
                content=content,
                status=status,
                token_input=token_input,
                token_output=token_output,
                tool_calls=tool_calls or [],
                completed_at=datetime.utcnow(),
            )
        )


class UsageService:
    @staticmethod
    async def create_usage_log(
        db: AsyncSession,
        tenant_id: str,
        user_id: str,
        conversation_id: str,
        request_id: str,
        agent_id: str,
        prompt_version: str,
        policy_version: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        tool_call_count: int,
        tool_calls: list,
        latency_ms: int,
        cost: float,
        error_code: str = None,
    ) -> UsageLog:
        usage_id = generate_id("usage")
        usage = UsageLog(
            tenant_id=tenant_id,
            id=usage_id,
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
            tool_calls=tool_calls,
            latency_ms=latency_ms,
            cost=cost,
            error_code=error_code,
        )
        db.add(usage)
        await db.flush()
        return usage


class AuditService:
    @staticmethod
    async def log(
        db: AsyncSession,
        tenant_id: str,
        operator_user_id: str,
        event_type: str,
        conversation_id: str = None,
        request_id: str = None,
        payload: dict = None,
    ):
        audit_id = generate_id("audit")
        audit = AuditLog(
            tenant_id=tenant_id,
            id=audit_id,
            operator_user_id=operator_user_id,
            conversation_id=conversation_id,
            request_id=request_id,
            event_type=event_type,
            payload=payload or {},
        )
        db.add(audit)
        await db.flush()
        return audit
