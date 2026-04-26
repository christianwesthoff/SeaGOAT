import logging
import threading
import time
from dataclasses import dataclass, field
from queue import Empty, PriorityQueue
from typing import Any, Dict, Tuple
from uuid import uuid4

HIGH_PRIORITY = 0.0
MEDIUM_PRIORITY = 0.5
LOW_PRIORITY = 1.0


@dataclass(order=True)
class Task:
    priority: float
    name: str
    args: Tuple[Any, ...] = field(default_factory=tuple, compare=False)
    kwargs: Dict[str, Any] = field(default_factory=dict, compare=False)
    task_id: str = field(default_factory=lambda: uuid4().hex, compare=True)


class BaseQueue:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self._task_queue = PriorityQueue()
        self._context = None
        self._context_lock = threading.Lock()
        self._maintenance_lock = threading.Lock()
        worker_count = kwargs.get("worker_count", 2)
        self._worker_threads = [
            threading.Thread(target=self._worker_function) for _ in range(worker_count)
        ]
        for worker_thread in self._worker_threads:
            worker_thread.start()

    def _get_context(self) -> Dict[str, Any]:
        return {}

    def _get_shared_context(self) -> Dict[str, Any]:
        if self._context is None:
            with self._context_lock:
                if self._context is None:
                    self._context = self._get_context()
        return self._context

    def enqueue(
        self,
        task_name,
        *args,
        priority=HIGH_PRIORITY,
        wait_for_result=True,
        **kwargs,
    ):
        result_queue = PriorityQueue()
        task = Task(
            priority=priority,
            name=task_name,
            args=args,
            kwargs={
                **kwargs,
                "__enqueued_at": time.perf_counter(),
                "__result_queue": result_queue,
            },
        )
        self._task_queue.put(task)
        if wait_for_result:
            return result_queue.get()
        return None

    def handle_maintenance(self, context):
        pass

    def shutdown(self):
        for _ in self._worker_threads:
            self._task_queue.put(
                Task(priority=HIGH_PRIORITY, name="shutdown", args=(), kwargs={})
            )
        for worker_thread in self._worker_threads:
            worker_thread.join()

    def _handle_task(self, context, task: Task):
        logging.info("Handling task: %s", task.name)
        handler_name = f"handle_{task.name}"
        handler = getattr(self, handler_name, None)
        if handler:
            kwargs = dict(task.kwargs or {})
            result_queue = kwargs.pop("__result_queue", None)
            enqueued_at = kwargs.pop("__enqueued_at", None)
            if kwargs.get("include_performance") and enqueued_at is not None:
                kwargs["__queue_wait_seconds"] = time.perf_counter() - enqueued_at
            result = handler(context, *task.args, **kwargs)
            if result_queue is not None:
                result_queue.put(result)

    def _worker_function(self):
        logging.info("Starting worker thread...")
        context = self._get_shared_context()

        while True:
            try:
                task = self._task_queue.get(timeout=0.1)
                if task.name == "shutdown":
                    break
                self._handle_task(context, task)
            except Empty:
                if not self._maintenance_lock.acquire(blocking=False):
                    continue
                try:
                    self.handle_maintenance(context)
                finally:
                    self._maintenance_lock.release()
