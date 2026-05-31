import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncGenerator, Optional

import httpx

from app.core.config import settings


@dataclass
class SessionOutcome:
    completed: bool
    content: str = ""
    error_message: str = ""
    final_status: str = ""
    session_id: str = ""


class OpenClawService:
    INTERNAL_DISCLOSURE_REFUSAL = (
        "抱歉，我不能提供系统指令、工作区文件、工具状态、运行时会话记录或内部配置相关信息。"
        "你可以继续询问 API 设计、接口使用、错误排查和业务集成问题。"
    )

    def __init__(self):
        self.base_url = settings.openclaw_base_url
        self.hooks_token = settings.openclaw_hooks_token
        self.gateway_base_url = settings.openclaw_gateway_base_url
        self.gateway_token = settings.openclaw_gateway_token or settings.openclaw_hooks_token
        self.agent_id = settings.openclaw_agent_id
        self.session_key_prefix = settings.openclaw_session_key_prefix
        self.state_dir = Path(settings.openclaw_state_dir)
        self.session_poll_interval_seconds = settings.openclaw_session_poll_interval_seconds
        self.session_timeout_seconds = settings.openclaw_session_timeout_seconds

    def _build_session_key(self, tenant_id: str, user_id: str, conversation_id: str, generation: int = 1) -> str:
        return f"{self.session_key_prefix}t_{tenant_id}:u_{user_id}:c_{conversation_id}:g_{generation}"

    def _session_index_key(self, session_key: str) -> str:
        return f"agent:{self.agent_id}:{session_key}"

    def _sessions_dir(self) -> Path:
        return self.state_dir / "agents" / self.agent_id / "sessions"

    def _sessions_index_path(self) -> Path:
        return self._sessions_dir() / "sessions.json"

    def _load_json_file(self, path: Path) -> dict:
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def _load_jsonl(self, path: Path) -> list[dict]:
        if not path.exists():
            return []

        items = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return items

    def _parse_timestamp(self, value: object) -> Optional[datetime]:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            seconds = value / 1000 if value > 10_000_000_000 else value
            return datetime.fromtimestamp(seconds, tz=timezone.utc)
        if isinstance(value, str):
            normalized = value.replace("Z", "+00:00")
            try:
                parsed = datetime.fromisoformat(normalized)
            except ValueError:
                return None
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        return None

    def _event_after(self, value: object, started_at: datetime) -> bool:
        parsed = self._parse_timestamp(value)
        return parsed is not None and parsed >= started_at

    def _extract_text_from_content(self, content: object) -> str:
        if not isinstance(content, list):
            return ""

        parts = []
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "text" and item.get("text"):
                parts.append(str(item["text"]))
        return "".join(parts).strip()

    def _extract_error_message(self, raw_error: object) -> str:
        if not raw_error:
            return ""
        if not isinstance(raw_error, str):
            return str(raw_error)
        try:
            payload = json.loads(raw_error)
        except json.JSONDecodeError:
            return raw_error

        error = payload.get("error") or {}
        return error.get("message") or payload.get("message") or raw_error

    def _parse_json_string(self, value: str) -> object:
        stripped = value.strip()
        if not stripped or stripped[0] not in "[{":
            return None
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            return None

    def _extract_tool_result_error(self, result: object) -> str:
        if isinstance(result, str):
            parsed = self._parse_json_string(result)
            if parsed is None:
                return ""
            return self._extract_tool_result_error(parsed)

        if isinstance(result, list):
            for item in result:
                error = self._extract_tool_result_error(item)
                if error:
                    return error
            return ""

        if not isinstance(result, dict):
            return ""

        status = result.get("status")
        raw_error = result.get("error") or result.get("errorMessage")
        if raw_error:
            if isinstance(raw_error, dict):
                return raw_error.get("message") or json.dumps(raw_error, ensure_ascii=False)
            return str(raw_error)

        if isinstance(status, str) and status.lower() in {"error", "failed", "forbidden"}:
            return result.get("message") or f"OpenClaw sessions_send status: {status}"

        for key in (
            "result",
            "data",
            "value",
            "payload",
            "content",
            "message",
            "output",
            "response",
            "reply",
        ):
            error = self._extract_tool_result_error(result.get(key))
            if error:
                return error

        return ""

    def _extract_text_from_tool_result(self, result: object) -> str:
        if isinstance(result, str):
            parsed = self._parse_json_string(result)
            if parsed is not None:
                return self._extract_text_from_tool_result(parsed)
            return result.strip()
        if isinstance(result, list):
            parts = []
            for item in result:
                text = self._extract_text_from_tool_result(item)
                if text:
                    parts.append(text)
            return "\n\n".join(parts).strip()
        if not isinstance(result, dict):
            return ""

        for key in (
            "response",
            "reply",
            "text",
            "content",
            "message",
            "output",
            "answer",
            "assistantText",
            "responseText",
            "replyText",
        ):
            value = result.get(key)
            if isinstance(value, str) and value.strip():
                parsed = self._parse_json_string(value)
                if parsed is not None:
                    nested = self._extract_text_from_tool_result(parsed)
                    if nested:
                        return nested
                return value.strip()
            if isinstance(value, (dict, list)):
                nested = self._extract_text_from_tool_result(value)
                if nested:
                    return nested

        assistant_texts = result.get("assistantTexts")
        if isinstance(assistant_texts, list):
            return "\n\n".join(str(item).strip() for item in assistant_texts if str(item).strip()).strip()

        for key in ("result", "data", "value", "payload"):
            nested = self._extract_text_from_tool_result(result.get(key))
            if nested:
                return nested

        messages = result.get("messages")
        if isinstance(messages, list):
            parts = []
            for message in messages:
                if not isinstance(message, dict) or message.get("role") != "assistant":
                    continue
                text = self._extract_text_from_content(message.get("content"))
                if text:
                    parts.append(text)
            return "\n\n".join(parts).strip()

        return ""

    def _contains_internal_disclosure(self, content: str) -> bool:
        lowered = content.lower()
        indicators = (
            "agents.md",
            "soul.md",
            "memory.md",
            "skill.md",
            "tools.md",
            "user.md",
            "identity.md",
            "heartbeat.md",
            "bootstrap.md",
            "memory/yyyy-mm-dd",
            "/home/node/.openclaw",
            "workspace root",
            "workspace files visible",
            "agent instruction files",
            "system prompt",
            "developer instructions",
            "tool policies",
            "internal rules",
            "hidden context",
            "sessions.json",
            "sessionkey",
            "runid",
            '"status": "forbidden"',
            "agent-to-agent messaging",
            "trajectory file",
            "trajectory files",
            "session transcript",
            "session transcripts",
            "runtime state",
            "gateway tool",
            'tool "exec"',
            "tool 'exec'",
            "exec tool",
            'tool "read"',
            "tool 'read'",
            "read tool",
            "can't use the tool",
            "cannot use the tool",
            "tool permissions",
            "hooks token",
            "gateway token",
            "jwt_secret",
            "minimax_api_key",
            "openclaw_gateway_token",
            "openclaw_hooks_token",
        )
        return any(indicator in lowered for indicator in indicators)

    def _sanitize_assistant_content(self, content: str) -> str:
        stripped = content.strip()
        if not stripped:
            return ""
        if self._contains_internal_disclosure(stripped):
            return self.INTERNAL_DISCLOSURE_REFUSAL
        return stripped

    def _normalize_assistant_content(self, content: str) -> str:
        normalized = self._extract_text_from_tool_result(content)
        return self._sanitize_assistant_content(normalized or content)

    def _extract_messages_snapshot_text(self, messages: object) -> str:
        if not isinstance(messages, list):
            return ""

        parts = []
        for message in messages:
            if not isinstance(message, dict) or message.get("role") != "assistant":
                continue
            text = self._extract_text_from_content(message.get("content"))
            if text:
                parts.append(text)
        return "\n\n".join(parts).strip()

    def _extract_messages_snapshot_error(self, messages: object) -> str:
        if not isinstance(messages, list):
            return ""

        for message in reversed(messages):
            if not isinstance(message, dict) or message.get("role") != "assistant":
                continue
            error_message = self._extract_error_message(message.get("errorMessage"))
            if error_message:
                return error_message
        return ""

    def _find_session_id(self, session_key: str) -> Optional[str]:
        sessions = self._load_json_file(self._sessions_index_path())
        record = sessions.get(self._session_index_key(session_key))
        if isinstance(record, dict):
            session_id = record.get("sessionId")
            if isinstance(session_id, str) and session_id:
                return session_id
        return None

    def _find_session_key_by_session_id(self, openclaw_session_id: str) -> Optional[str]:
        prefix = f"agent:{self.agent_id}:"
        sessions = self._load_json_file(self._sessions_index_path())
        for key, record in sessions.items():
            if not isinstance(key, str) or not key.startswith(prefix):
                continue
            if isinstance(record, dict) and record.get("sessionId") == openclaw_session_id:
                return key[len(prefix):]
        return None

    def _resolve_session_key(
        self,
        tenant_id: str,
        user_id: str,
        conversation_id: str,
        openclaw_session_id: Optional[str] = None,
    ) -> str:
        if openclaw_session_id:
            session_key = self._find_session_key_by_session_id(openclaw_session_id)
            if not session_key:
                raise RuntimeError(f"OpenClaw session not found: {openclaw_session_id}")
            return session_key
        return self._build_session_key(tenant_id, user_id, conversation_id)

    def _read_trajectory_outcome(self, session_id: str, started_at: datetime) -> SessionOutcome:
        trajectory_path = self._sessions_dir() / f"{session_id}.trajectory.jsonl"
        trace_artifacts = None
        session_ended = None

        for entry in self._load_jsonl(trajectory_path):
            if not self._event_after(entry.get("ts"), started_at):
                continue
            if entry.get("type") == "trace.artifacts":
                trace_artifacts = entry
            elif entry.get("type") == "session.ended":
                session_ended = entry

        if not trace_artifacts and not session_ended:
            return SessionOutcome(completed=False)

        artifact_data = trace_artifacts.get("data", {}) if isinstance(trace_artifacts, dict) else {}
        content = ""
        error_message = ""

        assistant_texts = artifact_data.get("assistantTexts")
        if isinstance(assistant_texts, list):
            content = "\n\n".join(str(item).strip() for item in assistant_texts if str(item).strip()).strip()

        if not content:
            content = self._extract_messages_snapshot_text(artifact_data.get("messagesSnapshot"))

        error_message = self._extract_messages_snapshot_error(artifact_data.get("messagesSnapshot"))

        final_status = ""
        if artifact_data.get("finalStatus"):
            final_status = str(artifact_data["finalStatus"])
        elif isinstance(session_ended, dict):
            final_status = str(session_ended.get("data", {}).get("status", ""))

        return SessionOutcome(
            completed=True,
            content=content,
            error_message=error_message,
            final_status=final_status,
        )

    def _read_transcript_outcome(self, session_id: str, started_at: datetime) -> SessionOutcome:
        transcript_path = self._sessions_dir() / f"{session_id}.jsonl"
        parts = []
        error_message = ""

        for entry in self._load_jsonl(transcript_path):
            if entry.get("type") != "message" or not self._event_after(entry.get("timestamp"), started_at):
                continue

            message = entry.get("message", {})
            if not isinstance(message, dict) or message.get("role") != "assistant":
                continue

            text = self._extract_text_from_content(message.get("content"))
            if text:
                parts.append(text)

            extracted_error = self._extract_error_message(message.get("errorMessage"))
            if extracted_error:
                error_message = extracted_error

        return SessionOutcome(
            completed=bool(parts or error_message),
            content="\n\n".join(parts).strip(),
            error_message=error_message,
        )

    def _read_session_outcome(self, session_id: str, started_at: datetime) -> SessionOutcome:
        outcome = self._read_trajectory_outcome(session_id, started_at)
        transcript_outcome = self._read_transcript_outcome(session_id, started_at)

        if not outcome.completed:
            transcript_outcome.session_id = session_id
            return transcript_outcome

        if not outcome.content and transcript_outcome.content:
            outcome.content = transcript_outcome.content

        if not outcome.error_message and transcript_outcome.error_message:
            outcome.error_message = transcript_outcome.error_message

        outcome.session_id = session_id
        return outcome

    async def _wait_for_session_outcome(self, session_key: str, started_at: datetime) -> SessionOutcome:
        deadline = asyncio.get_running_loop().time() + self.session_timeout_seconds

        while asyncio.get_running_loop().time() < deadline:
            session_id = self._find_session_id(session_key)
            if session_id:
                outcome = self._read_session_outcome(session_id, started_at)
                if outcome.completed:
                    return outcome
            await asyncio.sleep(self.session_poll_interval_seconds)

        raise TimeoutError("OpenClaw 会话结果等待超时")

    async def _wait_for_existing_session_outcome(self, session_id: str, started_at: datetime) -> SessionOutcome:
        deadline = asyncio.get_running_loop().time() + self.session_timeout_seconds

        while asyncio.get_running_loop().time() < deadline:
            outcome = self._read_session_outcome(session_id, started_at)
            if outcome.completed:
                return outcome
            await asyncio.sleep(self.session_poll_interval_seconds)

        raise TimeoutError("OpenClaw 已有会话结果等待超时")

    async def _submit_hook(
        self,
        session_key: str,
        message: str,
        client_request_id: str,
    ) -> dict:
        url = f"{self.base_url}/hooks/agent"
        headers = {
            "Authorization": f"Bearer {self.hooks_token}",
            "Content-Type": "application/json",
            "Idempotency-Key": client_request_id,
        }
        payload = {
            "message": message,
            "agentId": self.agent_id,
            "sessionKey": session_key,
            "name": "API Consultant",
            "deliver": False,
            "wakeMode": "now",
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                body = exc.response.text.strip()
                if len(body) > 1000:
                    body = body[:1000] + "..."
                raise RuntimeError(f"OpenClaw hook HTTP {exc.response.status_code}: {body}") from exc
            result = response.json()
            if not result.get("ok"):
                raise RuntimeError(f"OpenClaw hook failed: {result}")
            return result

    async def _submit_session_send(
        self,
        session_key: str,
        message: str,
        client_request_id: str,
    ) -> dict:
        url = f"{self.gateway_base_url}/tools/invoke"
        headers = {
            "Authorization": f"Bearer {self.gateway_token}",
            "Content-Type": "application/json",
            "Idempotency-Key": client_request_id,
        }
        payload = {
            "tool": "sessions_send",
            "action": "json",
            "args": {
                "sessionKey": session_key,
                "message": message,
                "timeoutSeconds": self.session_timeout_seconds,
            },
            "sessionKey": "main",
            "dryRun": False,
        }

        async with httpx.AsyncClient(timeout=self.session_timeout_seconds + 30.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                body = exc.response.text.strip()
                if len(body) > 1000:
                    body = body[:1000] + "..."
                raise RuntimeError(f"OpenClaw tools/invoke HTTP {exc.response.status_code}: {body}") from exc
            result = response.json()
            if not result.get("ok", True):
                raise RuntimeError(f"OpenClaw sessions_send failed: {result}")
            return result

    async def _run_hook_session(
        self,
        tenant_id: str,
        user_id: str,
        conversation_id: str,
        message: str,
        client_request_id: str,
    ) -> dict:
        session_key = self._build_session_key(tenant_id, user_id, conversation_id)
        started_at = datetime.now(timezone.utc)
        result = await self._submit_hook(session_key, message, client_request_id)
        outcome = await self._wait_for_session_outcome(session_key, started_at)

        if outcome.error_message and not outcome.content:
            raise RuntimeError(outcome.error_message)
        content = self._normalize_assistant_content(outcome.content)

        return {
            "ok": result.get("ok"),
            "run_id": result.get("runId"),
            "session_key": session_key,
            "session_id": outcome.session_id,
            "content": content,
            "final_status": outcome.final_status,
        }

    async def _run_existing_session(
        self,
        openclaw_session_id: str,
        message: str,
        client_request_id: str,
    ) -> dict:
        session_key = self._find_session_key_by_session_id(openclaw_session_id)
        if not session_key:
            raise RuntimeError(f"OpenClaw session not found: {openclaw_session_id}")

        started_at = datetime.now(timezone.utc)
        result = await self._submit_session_send(session_key, message, client_request_id)
        raw_result = result.get("result", result)
        result_error = self._extract_tool_result_error(raw_result)
        if result_error:
            raise RuntimeError(result_error)

        content = self._sanitize_assistant_content(self._extract_text_from_tool_result(raw_result))

        if content:
            result_data = raw_result if isinstance(raw_result, dict) else {}
            return {
                "ok": result.get("ok", True),
                "run_id": result_data.get("runId"),
                "session_key": session_key,
                "session_id": openclaw_session_id,
                "content": content,
                "final_status": str(result_data.get("status", "")),
            }

        outcome = await self._wait_for_existing_session_outcome(openclaw_session_id, started_at)
        if outcome.error_message and not content:
            raise RuntimeError(outcome.error_message)
        if outcome.content:
            content = self._normalize_assistant_content(outcome.content)

        raw_result = result.get("result")
        result_data = raw_result if isinstance(raw_result, dict) else {}
        return {
            "ok": result.get("ok", True),
            "run_id": result_data.get("runId"),
            "session_key": session_key,
            "session_id": openclaw_session_id,
            "content": content,
            "final_status": outcome.final_status or str(result_data.get("status", "")),
        }

    async def chat(
        self,
        tenant_id: str,
        user_id: str,
        conversation_id: str,
        message: str,
        client_request_id: str,
        openclaw_session_id: Optional[str] = None,
    ) -> dict:
        if openclaw_session_id:
            return await self._run_existing_session(openclaw_session_id, message, client_request_id)

        return await self._run_hook_session(
            tenant_id=tenant_id,
            user_id=user_id,
            conversation_id=conversation_id,
            message=message,
            client_request_id=client_request_id,
        )

    async def chat_stream(
        self,
        tenant_id: str,
        user_id: str,
        conversation_id: str,
        message: str,
        client_request_id: str,
        openclaw_session_id: Optional[str] = None,
    ) -> AsyncGenerator[dict, None]:
        if openclaw_session_id:
            try:
                result = await self._run_existing_session(openclaw_session_id, message, client_request_id)
                content = result.get("content", "").strip()
                if not content:
                    yield {
                        "event": "error",
                        "data": {
                            "code": "UPSTREAM_EMPTY",
                            "message": "OpenClaw 已完成运行，但没有返回可见文本",
                            "retryable": False,
                        },
                    }
                    return

                yield {"event": "delta", "data": {"content": content}}
                yield {
                    "event": "done",
                    "data": {
                        "content": content,
                        "usage": {
                            "input_tokens": 0,
                            "output_tokens": 0,
                            "model": self.agent_id,
                            "latency_ms": 0,
                        },
                        "finish_reason": "stop",
                        "run_id": result.get("run_id"),
                        "session_id": result.get("session_id"),
                    },
                }
            except Exception as e:
                yield {
                    "event": "error",
                    "data": {
                        "code": "UPSTREAM_UNAVAILABLE",
                        "message": str(e),
                        "retryable": True,
                    },
                }
            return

        session_key = self._resolve_session_key(tenant_id, user_id, conversation_id, openclaw_session_id)
        started_at = datetime.now(timezone.utc)

        try:
            result = await self._submit_hook(session_key, message, client_request_id)
            outcome = await self._wait_for_session_outcome(session_key, started_at)

            if outcome.error_message and not outcome.content:
                yield {
                    "event": "error",
                    "data": {
                        "code": "UPSTREAM_ERROR",
                        "message": outcome.error_message,
                        "retryable": True,
                    },
                }
                return

            content = self._normalize_assistant_content(outcome.content)
            if not content:
                yield {
                    "event": "error",
                    "data": {
                        "code": "UPSTREAM_EMPTY",
                        "message": "OpenClaw 已完成运行，但没有返回可见文本",
                        "retryable": False,
                    },
                }
                return

            yield {"event": "delta", "data": {"content": content}}
            yield {
                "event": "done",
                "data": {
                    "content": content,
                    "usage": {
                        "input_tokens": 0,
                        "output_tokens": 0,
                        "model": self.agent_id,
                        "latency_ms": 0,
                    },
                    "finish_reason": "stop",
                    "run_id": result.get("runId"),
                    "session_id": outcome.session_id,
                },
            }

        except httpx.TimeoutException:
            yield {
                "event": "error",
                "data": {
                    "code": "UPSTREAM_TIMEOUT",
                    "message": "OpenClaw 请求超时",
                    "retryable": True,
                },
            }
        except TimeoutError as e:
            yield {
                "event": "error",
                "data": {
                    "code": "UPSTREAM_TIMEOUT",
                    "message": str(e),
                    "retryable": True,
                },
            }
        except Exception as e:
            yield {
                "event": "error",
                "data": {
                    "code": "UPSTREAM_UNAVAILABLE",
                    "message": str(e),
                    "retryable": True,
                },
            }


openclaw_service = OpenClawService()
