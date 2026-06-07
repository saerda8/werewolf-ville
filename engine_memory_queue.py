from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
import time
from typing import Any
import uuid


@dataclass
class TypedMemoryEntry:
    """类型化记忆条目，包含丰富字段以供未来检索。"""
    id: str = ""
    type: str = "event"  # event|chat|thought|plan
    created_at: float = 0.0
    day: int = 0
    game_hour: int = 0
    subject: str = ""
    predicate: str = ""
    object: str = ""
    text: str = ""
    importance: int = 1
    keywords: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    source: str = ""
    visibility: str = "public"  # public|private|internal


@dataclass
class MemoryTask:
    task_id: str
    agent_name: str
    payload: dict[str, Any]
    created_at: float = field(default_factory=time.time)
    retry_count: int = 0
    max_retries: int = 3
    status: str = "pending"  # pending|processing|completed|failed


class MemoryQueue:
    def __init__(self, max_retries: int = 3) -> None:
        self._items: deque[MemoryTask] = deque()
        self._failed_items: list[MemoryTask] = []
        self._max_retries = max_retries

    def enqueue(self, task: MemoryTask) -> None:
        self._items.append(task)

    def pop_next(self) -> MemoryTask | None:
        if not self._items:
            return None
        task = self._items.popleft()
        task.status = "processing"
        return task

    def mark_failed(self, task: MemoryTask) -> None:
        """标记任务失败；若仍有重试次数则重新排队，否则移入失败列表。"""
        task.retry_count += 1
        if task.retry_count >= self._max_retries:
            task.status = "failed"
            self._failed_items.append(task)
        else:
            task.status = "pending"
            self._items.appendleft(task)

    def retry_failed_tasks(self) -> int:
        """重试所有仍未耗尽重试次数的失败任务。返回重试数量。"""
        count = 0
        remaining = []
        for task in self._failed_items:
            if task.retry_count < self._max_retries:
                task.status = "pending"
                self._items.appendleft(task)
                count += 1
            else:
                remaining.append(task)
        self._failed_items = remaining
        return count

    def get_failed_tasks(self) -> list[MemoryTask]:
        """返回所有已失败（耗尽重试）的任务列表。"""
        return list(self._failed_items)

    def enqueue_typed_memory(self, agent_name: str, entry: TypedMemoryEntry) -> MemoryTask:
        """将类型化记忆条目包装为任务并入队。"""
        task = MemoryTask(
            task_id=entry.id or str(uuid.uuid4()),
            agent_name=agent_name,
            payload={
                "typed_memory": {
                    "id": entry.id,
                    "type": entry.type,
                    "created_at": entry.created_at,
                    "day": entry.day,
                    "game_hour": entry.game_hour,
                    "subject": entry.subject,
                    "predicate": entry.predicate,
                    "object": entry.object,
                    "text": entry.text,
                    "importance": entry.importance,
                    "keywords": entry.keywords,
                    "evidence": entry.evidence,
                    "source": entry.source,
                    "visibility": entry.visibility,
                }
            },
        )
        self.enqueue(task)
        return task

    def __len__(self) -> int:
        return len(self._items)
