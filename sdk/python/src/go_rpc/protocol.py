from dataclasses import dataclass
from typing import Any, Mapping


MAX_MESSAGE_BYTES = 10 * 1024 * 1024
PROTOCOL_VERSION = 1
INVOCATION_CONTEXT_CAPABILITY = "invocation_context.v1"


@dataclass(frozen=True)
class InvocationContext:
    sequence: str
    trace_id: str
    group: str
    action: str
    client_id: str
    deadline_unix_ms: int
    idempotent: bool
    idempotency_key: str
    attempt: int

    @classmethod
    def from_message(cls, message: Mapping[str, Any]) -> "InvocationContext":
        if type(message) is not dict:
            raise ValueError("invoke message must be a dict")
        raw = message.get("__rpc_context__")
        required = {
            "sequence", "trace_id", "group", "action", "client_id",
            "deadline_unix_ms", "idempotent", "idempotency_key", "attempt",
        }
        if type(raw) is not dict or set(raw) != required:
            raise ValueError("invoke context must contain exactly nine fields")
        for field in ("sequence", "trace_id", "group", "action", "client_id", "idempotency_key"):
            if type(raw[field]) is not str:
                raise ValueError(f"invoke context field {field} must be a string")
        for field in ("deadline_unix_ms", "attempt"):
            value = raw[field]
            if type(value) is not int or isinstance(value, bool) or value < 0:
                raise ValueError(f"invoke context field {field} must be a non-negative integer")
        if type(raw["idempotent"]) is not bool:
            raise ValueError("invoke context field idempotent must be a boolean")
        return cls(**raw)
