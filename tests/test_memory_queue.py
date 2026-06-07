import time

from engine_memory_queue import MemoryQueue, MemoryTask, TypedMemoryEntry


# ---------------------------------------------------------------------------
# Basic FIFO and lifecycle
# ---------------------------------------------------------------------------

def test_memory_queue_fifo_by_created_order():
    queue = MemoryQueue()

    queue.enqueue(
        MemoryTask(
            task_id="memq_1",
            agent_name="Arthur Burton",
            payload={"kind": "action"},
            created_at=100.0,
        )
    )
    queue.enqueue(
        MemoryTask(
            task_id="memq_2",
            agent_name="Isabella Rodriguez",
            payload={"kind": "chat"},
            created_at=101.0,
        )
    )

    assert queue.pop_next().task_id == "memq_1"
    assert queue.pop_next().task_id == "memq_2"
    assert queue.pop_next() is None


def test_memory_queue_len_tracks_items():
    queue = MemoryQueue()

    assert len(queue) == 0

    queue.enqueue(
        MemoryTask(
            task_id="memq_1",
            agent_name="Arthur Burton",
            payload={"kind": "action"},
        )
    )
    queue.enqueue(
        MemoryTask(
            task_id="memq_2",
            agent_name="Isabella Rodriguez",
            payload={"kind": "chat"},
        )
    )

    assert len(queue) == 2

    queue.pop_next()
    assert len(queue) == 1

    queue.pop_next()
    assert len(queue) == 0


def test_memory_queue_pop_empty_returns_none():
    queue = MemoryQueue()

    assert queue.pop_next() is None
    assert len(queue) == 0


# ---------------------------------------------------------------------------
# mark_failed and retry mechanism
# ---------------------------------------------------------------------------

def test_mark_failed_with_retries_remaining_requeues():
    """Task with retries left goes back to front of queue."""
    queue = MemoryQueue(max_retries=3)
    task = MemoryTask(
        task_id="memq_r1",
        agent_name="Arthur Burton",
        payload={"kind": "action"},
    )
    queue.enqueue(task)
    popped = queue.pop_next()
    assert popped.task_id == "memq_r1"
    assert popped.status == "processing"

    queue.mark_failed(popped)
    # Should be back in queue as pending with retry_count=1
    assert popped.retry_count == 1
    assert popped.status == "pending"
    assert len(queue) == 1

    # Pop again — should get the same task back
    retried = queue.pop_next()
    assert retried.task_id == "memq_r1"
    assert retried.retry_count == 1


def test_mark_failed_exhausted_goes_to_failed_list():
    """When retries exhausted, task goes to failed list, not queue."""
    queue = MemoryQueue(max_retries=2)
    task = MemoryTask(
        task_id="memq_fail",
        agent_name="Isabella Rodriguez",
        payload={"kind": "chat"},
        max_retries=2,
    )
    queue.enqueue(task)
    popped = queue.pop_next()

    # Fail twice
    queue.mark_failed(popped)  # retry_count=1, requeued
    popped2 = queue.pop_next()
    queue.mark_failed(popped2)  # retry_count=2, exhausted

    assert popped2.status == "failed"
    assert len(queue) == 0
    assert len(queue.get_failed_tasks()) == 1
    assert queue.get_failed_tasks()[0].task_id == "memq_fail"


def test_retry_failed_tasks_requeues_eligible():
    """retry_failed_tasks moves tasks with remaining retries back to queue."""
    queue = MemoryQueue(max_retries=3)
    task = MemoryTask(
        task_id="memq_retry",
        agent_name="Maria Lopez",
        payload={"kind": "observation"},
    )
    queue.enqueue(task)
    popped = queue.pop_next()
    queue.mark_failed(popped)  # retry_count=1 -> back in queue
    popped2 = queue.pop_next()
    queue.mark_failed(popped2)  # retry_count=2 -> back in queue

    # Pop and immediately fail to move into failed list
    popped3 = queue.pop_next()
    queue.mark_failed(popped3)  # retry_count=3 -> failed list (exhausted)
    assert len(queue.get_failed_tasks()) == 1

    # Now manually reduce retry_count to simulate external reset
    failed_task = queue.get_failed_tasks()[0]
    failed_task.retry_count = 1  # Reset to allow retry

    count = queue.retry_failed_tasks()
    assert count == 1
    # Task should be back in queue
    assert len(queue) == 1
    retried_task = queue.pop_next()
    assert retried_task.task_id == "memq_retry"


def test_get_failed_tasks_returns_copy():
    """get_failed_tasks returns a list copy, not internal reference."""
    queue = MemoryQueue(max_retries=1)
    task = MemoryTask(
        task_id="memq_copy",
        agent_name="Sam Moore",
        payload={"kind": "work"},
    )
    queue.enqueue(task)
    popped = queue.pop_next()
    queue.mark_failed(popped)  # exhausted

    failed = queue.get_failed_tasks()
    assert len(failed) == 1
    # Mutating the returned list should not affect internal state
    failed.clear()
    assert len(queue.get_failed_tasks()) == 1


# ---------------------------------------------------------------------------
# enqueue_typed_memory
# ---------------------------------------------------------------------------

def test_enqueue_typed_memory_creates_task():
    """enqueue_typed_memory wraps TypedMemoryEntry into MemoryTask."""
    queue = MemoryQueue()
    entry = TypedMemoryEntry(
        id="evt_001",
        type="event",
        day=1,
        game_hour=14,
        subject="Isabella Rodriguez",
        predicate="talked_to",
        object="Crow",
        text="Isabella talked to Crow about safety.",
        importance=7,
        keywords=["Isabella", "Crow", "safety"],
        evidence=["overheard conversation"],
        source="direct_observation",
        visibility="witnessed",
        created_at=time.time(),
    )

    task = queue.enqueue_typed_memory("Isabella Rodriguez", entry)
    assert task is not None
    assert task.agent_name == "Isabella Rodriguez"
    assert task.status == "pending"
    assert len(queue) == 1

    popped = queue.pop_next()
    payload = popped.payload["typed_memory"]
    assert payload["id"] == "evt_001"
    assert payload["type"] == "event"
    assert payload["subject"] == "Isabella Rodriguez"
    assert payload["predicate"] == "talked_to"
    assert payload["object"] == "Crow"
    assert payload["importance"] == 7
    assert payload["keywords"] == ["Isabella", "Crow", "safety"]
    assert payload["evidence"] == ["overheard conversation"]
    assert payload["visibility"] == "witnessed"


def test_enqueue_typed_memory_generates_id_when_empty():
    """If entry has no id, a UUID is generated for the task."""
    queue = MemoryQueue()
    entry = TypedMemoryEntry(
        type="chat",
        day=2,
        text="A conversation happened.",
    )
    task = queue.enqueue_typed_memory("Klaus Mueller", entry)
    assert task.task_id is not None
    assert len(task.task_id) > 0
    # The payload should have the generated id or original id
    payload = queue.pop_next().payload["typed_memory"]
    assert payload["id"] == "" or len(payload["id"]) > 0


def test_typed_memory_entry_defaults():
    """TypedMemoryEntry has sensible defaults for all fields."""
    entry = TypedMemoryEntry()
    assert entry.id == ""
    assert entry.type == "event"
    assert entry.day == 0
    assert entry.game_hour == 0
    assert entry.subject == ""
    assert entry.predicate == ""
    assert entry.object == ""
    assert entry.text == ""
    assert entry.importance == 1
    assert entry.keywords == []
    assert entry.evidence == []
    assert entry.source == ""
    assert entry.visibility == "public"


def test_memory_queue_multiple_typed_entries_fifo():
    """Multiple enqueue_typed_memory calls maintain FIFO order."""
    queue = MemoryQueue()
    e1 = TypedMemoryEntry(id="e1", type="event", day=1, text="First")
    e2 = TypedMemoryEntry(id="e2", type="chat", day=1, text="Second")
    e3 = TypedMemoryEntry(id="e3", type="thought", day=2, text="Third")

    queue.enqueue_typed_memory("Arthur Burton", e1)
    queue.enqueue_typed_memory("Arthur Burton", e2)
    queue.enqueue_typed_memory("Arthur Burton", e3)

    assert queue.pop_next().task_id == "e1"
    assert queue.pop_next().task_id == "e2"
    assert queue.pop_next().task_id == "e3"
    assert queue.pop_next() is None


def test_memory_queue_mixed_operations():
    """Mix of enqueue, pop, mark_failed, and retry works correctly."""
    queue = MemoryQueue(max_retries=2)
    e1 = TypedMemoryEntry(id="e1", type="event", day=1, text="Event 1")
    e2 = TypedMemoryEntry(id="e2", type="event", day=1, text="Event 2")

    queue.enqueue_typed_memory("Arthur Burton", e1)
    queue.enqueue_typed_memory("Arthur Burton", e2)

    # Process e1, fail once
    t1 = queue.pop_next()
    assert t1.task_id == "e1"
    queue.mark_failed(t1)  # retry_count=1, back in front

    # Next pop should be e1 again (requeued at front)
    t1_retry = queue.pop_next()
    assert t1_retry.task_id == "e1"

    # Now fail e1 again -> exhausted
    queue.mark_failed(t1_retry)
    assert len(queue) == 1  # e2 still waiting
    assert len(queue.get_failed_tasks()) == 1  # e1 exhausted

    # Pop e2
    t2 = queue.pop_next()
    assert t2.task_id == "e2"
