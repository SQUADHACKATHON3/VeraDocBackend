import threading
from collections.abc import Callable
from typing import Any


def run_in_background(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
    """Fire-and-forget background work (replaces FastAPI BackgroundTasks)."""
    thread = threading.Thread(target=fn, args=args, kwargs=kwargs, daemon=True)
    thread.start()
