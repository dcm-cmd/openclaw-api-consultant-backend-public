from pydantic import BaseModel, Field
from typing import Optional, List, Literal


class ChatRequest(BaseModel):
    conversation_id: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1)
    client_request_id: str = Field(..., min_length=1)


class ChatStreamRequest(BaseModel):
    conversation_id: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1)
    client_request_id: str = Field(..., min_length=1)


class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""
    latency_ms: int = 0


class ChatResponse(BaseModel):
    id: str
    conversation_id: str
    content: Optional[str] = ""
    usage: Optional[Usage] = None
    openclaw_session_id: Optional[str] = None


class ChatStreamDelta(BaseModel):
    content: str


class ChatStreamStart(BaseModel):
    id: str
    conversation_id: str
    client_request_id: str
    created_at: str


class ChatStreamToolCall(BaseModel):
    tool: str
    input: dict
    call_id: str


class ChatStreamToolCallDone(BaseModel):
    tool: str
    output: str
    call_id: str


class ChatStreamDone(BaseModel):
    id: str
    content: str
    usage: Usage
    finish_reason: Literal["stop", "length", "tool_calls"]
    openclaw_session_id: Optional[str] = None


class ChatStreamError(BaseModel):
    id: str
    code: str
    message: str
    retryable: bool


class ConversationCreate(BaseModel):
    title: str = "新的咨询"
    agent_id: str = "consultant-main"


class ConversationResponse(BaseModel):
    conversation_id: str
    agent_id: str
    title: str
    status: str = "active"
    created_at: str


class MessageResponse(BaseModel):
    id: str
    conversation_id: str
    role: str
    content: str
    status: str
    created_at: str


class ErrorDetail(BaseModel):
    code: str
    message: str
    request_id: Optional[str] = None


class ErrorResponse(BaseModel):
    error: ErrorDetail
