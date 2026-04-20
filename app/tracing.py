from __future__ import annotations

import os
from typing import Any

try:
    from langfuse import Langfuse

    _langfuse_client: Langfuse | None = Langfuse(
        public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
        secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
        base_url=os.getenv("LANGFUSE_BASE_URL", "http://localhost:27100"),
    )
except Exception:  # pragma: no cover
    _langfuse_client = None

    class _DummyLangfuse:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass
        def auth_check(self) -> bool:
            return False
        def flush(self) -> None:
            pass
        def shutdown(self) -> None:
            pass
        def start_as_current_observation(self, *args: Any, **kwargs: Any):
            return _DummySpan()
        def update_current_trace(self, *args: Any, **kwargs: Any) -> None:
            pass

    class _DummySpan:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def start_as_current_observation(self, *args: Any, **kwargs: Any):
            return _DummySpan()
        def update(self, *args: Any, **kwargs: Any) -> None:
            pass

    Langfuse = _DummyLangfuse  # type: ignore


def get_langfuse_client() -> Langfuse | None:
    return _langfuse_client


def tracing_enabled() -> bool:
    if _langfuse_client is None:
        return False
    try:
        return _langfuse_client.auth_check()
    except Exception:
        return False
