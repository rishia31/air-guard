"""In-process publish/subscribe that feeds the Server-Sent Events stream.

Topics are ``user:<id>`` for everything about one person (risk, check-ins,
alerts addressed to them) and ``community`` for map updates. ``publish`` is
safe to call from worker threads.
"""

from __future__ import annotations

import asyncio
import threading
import time
from collections import defaultdict


class Bus:
    def __init__(self, queue_size: int = 256):
        self._subs: dict[str, set[asyncio.Queue]] = defaultdict(set)
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._queue_size = queue_size

    def bind(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self, topics: list[str]) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=self._queue_size)
        with self._lock:
            for topic in topics:
                self._subs[topic].add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        with self._lock:
            for subs in self._subs.values():
                subs.discard(queue)

    def publish(self, topic: str, kind: str, data: dict) -> None:
        message = {"type": kind, "topic": topic, "ts": time.time(), "data": data}
        with self._lock:
            queues = list(self._subs.get(topic, ()))
        if not queues or self._loop is None or self._loop.is_closed():
            return
        try:
            on_loop = asyncio.get_running_loop() is self._loop
        except RuntimeError:
            on_loop = False
        for queue in queues:
            if on_loop:
                _put(queue, message)
            else:
                self._loop.call_soon_threadsafe(_put, queue, message)

    def user(self, user_id: str, kind: str, data: dict) -> None:
        self.publish(f"user:{user_id}", kind, data)


def _put(queue: asyncio.Queue, message: dict) -> None:
    if queue.full():  # slow client: drop the oldest message rather than block publishers
        try:
            queue.get_nowait()
        except asyncio.QueueEmpty:
            pass
    queue.put_nowait(message)
