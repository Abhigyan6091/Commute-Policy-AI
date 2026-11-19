"""Request-scoped LLM call budget enforcement (max 2 calls per request)."""
from contextvars import ContextVar

_call_count: ContextVar[int] = ContextVar('llm_call_count', default=0)
MAX_CALLS = 2

def reset() -> None:
    _call_count.set(0)

def increment() -> int:
    n = _call_count.get() + 1
    _call_count.set(n)
    return n

def get_count() -> int:
    return _call_count.get()

def check_budget() -> None:
    if get_count() >= MAX_CALLS:
        raise RuntimeError(f"LLM call budget exhausted: max {MAX_CALLS} calls per request")
