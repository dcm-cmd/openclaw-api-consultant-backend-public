import uuid
from datetime import datetime
from sqlalchemy import (
    Column,
    String,
    Integer,
    Boolean,
    Text,
    DateTime,
    ForeignKeyConstraint,
    UniqueConstraint,
    Index,
    JSON,
    Numeric,
    CheckConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from app.core.database import Base


def generate_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class User(Base):
    __tablename__ = "users"

    tenant_id = Column(String(64), nullable=False, primary_key=True)
    id = Column(String(64), nullable=False, primary_key=True)
    email = Column(String(255), nullable=True)
    phone = Column(String(32), nullable=True)
    external_id = Column(String(128), nullable=True)
    status = Column(String(16), nullable=False, default="active")
    plan = Column(String(16), nullable=False, default="free")
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("tenant_id", "email", name="users_tenant_email_uq"),
        Index("users_tenant_email_uq", "tenant_id", "email", unique=True, postgresql_where=email.isnot(None)),
    )


class Conversation(Base):
    __tablename__ = "conversations"

    tenant_id = Column(String(64), nullable=False, primary_key=True)
    id = Column(String(64), nullable=False, primary_key=True)
    user_id = Column(String(64), nullable=False)
    agent_id = Column(String(64), nullable=False, default="consultant-main")
    title = Column(String(255), nullable=False, default="新的咨询")
    status = Column(String(16), nullable=False, default="idle")
    openclaw_session_id = Column(String(256), nullable=True)
    session_generation = Column(Integer, nullable=False, default=0)
    prompt_version = Column(String(32), nullable=False, default="v1")
    policy_version = Column(String(32), nullable=False, default="policy-v1")
    summary = Column(Text, nullable=True)
    summary_version = Column(Integer, nullable=False, default=0)
    last_message_at = Column(DateTime(timezone=True), nullable=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "user_id"], ["users.tenant_id", "users.id"]),
        Index("conversations_user_last_message_idx", "tenant_id", "user_id", last_message_at.desc()),
        Index("conversations_active_session_uq", "tenant_id", "openclaw_session_id", unique=True,
              postgresql_where=openclaw_session_id.isnot(None)),
    )

    messages = relationship("Message", back_populates="conversation")
    chat_requests = relationship("ChatRequest", back_populates="conversation")


class ChatRequest(Base):
    __tablename__ = "chat_requests"

    tenant_id = Column(String(64), nullable=False, primary_key=True)
    id = Column(String(64), nullable=False, primary_key=True)
    conversation_id = Column(String(64), nullable=False)
    user_id = Column(String(64), nullable=False)
    client_request_id = Column(String(64), nullable=False)
    status = Column(String(16), nullable=False)
    agent_id = Column(String(64), nullable=False)
    prompt_version = Column(String(32), nullable=False)
    policy_version = Column(String(32), nullable=False)
    openclaw_session_id = Column(String(256), nullable=True)
    response_message_id = Column(String(64), nullable=True)
    error_code = Column(String(32), nullable=True)
    retry_count = Column(Integer, nullable=False, default=0)
    stream = Column(Boolean, nullable=False, default=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "conversation_id"], ["conversations.tenant_id", "conversations.id"]),
        ForeignKeyConstraint(["tenant_id", "user_id"], ["users.tenant_id", "users.id"]),
        UniqueConstraint("tenant_id", "user_id", "conversation_id", "client_request_id",
                         name="chat_requests_request_uq"),
        Index("chat_requests_status_idx", "tenant_id", "status", created_at.desc()),
        Index("chat_requests_conversation_idx", "tenant_id", "conversation_id", created_at.desc()),
        CheckConstraint("retry_count >= 0", name="chat_requests_retry_count_check"),
    )

    conversation = relationship("Conversation", back_populates="chat_requests")


class Message(Base):
    __tablename__ = "messages"

    tenant_id = Column(String(64), nullable=False, primary_key=True)
    id = Column(String(64), nullable=False, primary_key=True)
    conversation_id = Column(String(64), nullable=False)
    user_id = Column(String(64), nullable=False)
    request_id = Column(String(64), nullable=False)
    role = Column(String(16), nullable=False)
    status = Column(String(16), nullable=False)
    content = Column(Text, nullable=False, default="")
    tool_calls = Column(JSONB, nullable=False, default=list)
    token_input = Column(Integer, nullable=False, default=0)
    token_output = Column(Integer, nullable=False, default=0)
    error_code = Column(String(32), nullable=True)
    metadata_json = Column("metadata", JSONB, nullable=False, default=dict)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
          ForeignKeyConstraint(["tenant_id", "conversation_id"], ["conversations.tenant_id", "conversations.id"]),
          ForeignKeyConstraint(["tenant_id", "user_id"], ["users.tenant_id", "users.id"]),
          ForeignKeyConstraint(["tenant_id", "request_id"], ["chat_requests.tenant_id", "chat_requests.id"]),
        Index("messages_conversation_created_idx", "tenant_id", "conversation_id", created_at.asc()),
        Index("messages_request_idx", "tenant_id", "request_id"),
          Index("messages_user_once_per_request_uq", "tenant_id", "request_id", "role", unique=True,
              postgresql_where=role == "user"),
          Index("messages_assistant_once_per_request_uq", "tenant_id", "request_id", "role", unique=True,
              postgresql_where=role == "assistant"),
        Index("messages_status_idx", "tenant_id", "status", created_at.desc()),
    )

    conversation = relationship("Conversation", back_populates="messages")


class UsageLog(Base):
    __tablename__ = "usage_logs"

    tenant_id = Column(String(64), nullable=False, primary_key=True)
    id = Column(String(64), nullable=False, primary_key=True)
    user_id = Column(String(64), nullable=False)
    conversation_id = Column(String(64), nullable=False)
    request_id = Column(String(64), nullable=False)
    agent_id = Column(String(64), nullable=False)
    prompt_version = Column(String(32), nullable=False)
    policy_version = Column(String(32), nullable=False)
    model = Column(String(64), nullable=False)
    input_tokens = Column(Integer, nullable=False, default=0)
    output_tokens = Column(Integer, nullable=False, default=0)
    tool_call_count = Column(Integer, nullable=False, default=0)
    tool_calls = Column(JSONB, nullable=False, default=list)
    latency_ms = Column(Integer, nullable=False, default=0)
    cost = Column(Numeric(12, 6), nullable=False, default=0)
    error_code = Column(String(32), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "user_id"], ["users.tenant_id", "users.id"]),
        ForeignKeyConstraint(["tenant_id", "conversation_id"], ["conversations.tenant_id", "conversations.id"]),
        ForeignKeyConstraint(["tenant_id", "request_id"], ["chat_requests.tenant_id", "chat_requests.id"]),
        UniqueConstraint("tenant_id", "request_id", name="usage_logs_request_uq"),
        Index("usage_logs_user_created_idx", "tenant_id", "user_id", created_at.desc()),
        Index("usage_logs_conversation_created_idx", "tenant_id", "conversation_id", created_at.desc()),
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    tenant_id = Column(String(64), nullable=False, primary_key=True)
    id = Column(String(64), nullable=False, primary_key=True)
    operator_user_id = Column(String(64), nullable=True)
    conversation_id = Column(String(64), nullable=True)
    request_id = Column(String(64), nullable=True)
    event_type = Column(String(64), nullable=False)
    payload = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "operator_user_id"], ["users.tenant_id", "users.id"]),
        ForeignKeyConstraint(["tenant_id", "conversation_id"], ["conversations.tenant_id", "conversations.id"]),
        ForeignKeyConstraint(["tenant_id", "request_id"], ["chat_requests.tenant_id", "chat_requests.id"]),
        Index("audit_logs_event_type_idx", "tenant_id", "event_type", created_at.desc()),
        Index("audit_logs_conversation_idx", "tenant_id", "conversation_id", created_at.desc()),
    )