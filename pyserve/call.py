
__all__ = ["call"]

from threading import Thread
from typing import Any, Callable, Mapping


def call(func: Callable[..., Any], **kwargs) -> Thread:
    "calls <func> in a subthread and returns that thread"
    "thread is a daemon by default"
    default = {
        "daemon": True
        }
    use: Mapping[str, Any] = default | kwargs
    t = Thread(target=func, **use)
    t.start()
    return t
